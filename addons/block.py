import discord
from discord.ext import commands, flags
import typing
import re
from utils import checks, common


class Block(commands.Cog):
    """Block perms for users in desired channels"""

    def __init__(self, bot):
        self.bot = bot

    async def dbblocklist(self, member: discord.Member,
                          channel: typing.Union[discord.TextChannel, discord.VoiceChannel, discord.CategoryChannel],
                          blocktypes, mode, reason: str = None):
        """Adds a block to the db entry"""
        if mode == "block":
            async with self.bot.db.acquire() as conn:
                if not await conn.fetchval(
                        "SELECT userid FROM channel_block WHERE userid = $1 AND guildid = $2 AND channelid = $3",
                        member.id,
                        member.guild.id, channel.id):
                    await conn.execute(
                        "INSERT INTO channel_block (userid, guildid, channelid, blocktype, reason) VALUES ($1, $2, $3, $4, $5)",
                        member.id, member.guild.id, channel.id, blocktypes, reason)
                else:
                    await conn.execute(
                        "UPDATE channel_block SET blocktype = array_cat(blocktype, $1) WHERE userid = $2 AND channelid = $3",
                        blocktypes, member.id, channel.id)

        elif mode == "unblock":
            async with self.bot.db.acquire() as conn:
                if not await conn.fetchval("SELECT userid FROM channel_block WHERE userid = $1 AND channelid = $2",
                                           member.id, channel.id):
                    return False

                for b in blocktypes:
                    await conn.execute(
                        "UPDATE channel_block SET blocktype = array_remove(blocktype, $1) WHERE userid = $2 AND channelid = $3",
                        b, member.id, channel.id)
                    if not await conn.fetchval(
                            "SELECT blocktype FROM channel_block WHERE userid = $1 AND channelid = $2", member.id,
                            channel.id):
                        await conn.execute("DELETE FROM channel_block WHERE userid = $1 AND channelid = $2", member.id,
                                           channel.id)
                        break

                return True

    def get_guild_channels(self, guild: discord.Guild, channeldata: typing.Union[str, int]):
        """Tries to match an id with a channel's guilds"""
        if isinstance(channeldata, int) and channeldata in (c.id for c in guild.channels):
            return guild.get_channel(channeldata)
        elif isinstance(channeldata, str):
            return discord.utils.get(guild.channels, name=channeldata)
        else:
            raise commands.BadArgument("Invalid channel id")

    @commands.guild_only()
    @checks.is_staff_or_perms("Mod", manage_roles=True)
    @flags.add_flag("--view", '-v', action="store_true", default=False)
    @flags.add_flag("--embed", '-e', action="store_true", default=False)
    @flags.add_flag("--addreactions", '-a', action="store_true", default=False)
    @flags.add_flag("--channel", '-c', default=None)
    @flags.add_flag("--reason", '-r', type=str, default="", nargs="+")
    @flags.command()
    async def block(self, ctx, member: discord.Member, **flag_options):
        """
        Blocks a user's permission in a channel (Mod+ or manage roles)

        This command can be used to block a user from having certain permissions in specific channels or channel categories.
        The available flags are `--view` (`-v`) to block viewing perms, `--embed` (`-e`) to block embedding and attachment perms, and `--addreactions` (`-a`) to block reaction perms.
        The view flag can only be used by itself as there is no need to also block those other permissions while viewing is being blocked.
        Please note that if you block someone from a category it will only be applied to the channels that are synced with the category
        """
        modandbotprotection = await checks.modAndBotProtection(self.bot, ctx, member, "block")
        if modandbotprotection is not None:
            await ctx.send(modandbotprotection)
            return

        channel = flag_options.get('channel')
        if channel is None:
            channel = ctx.channel

        elif isinstance(channel, str):
            match = re.search(r'\d+', channel)
            cid = int(match.group()) if match is not None else channel
            channel = self.get_guild_channels(ctx.guild, cid)

        reason = None
        if flag_options.get('reason'):
            reason = ' '.join(flag_options['reason'])
        blockmsg = []
        if flag_options.get('view'):
            blockmsg.append("view")
            if await self.bot.db.fetchval(
                    "SELECT blocktype @> ARRAY['view'] FROM channel_block WHERE userid = $1 AND channelid = $2",
                    member.id, channel.id):
                return await ctx.send(f"{member} is already blocked from seeing {channel.mention}")
            try:
                channeloverwrites = channel.overwrites_for(member)
                channeloverwrites.read_messages = False
                await channel.set_permissions(member, overwrite=channeloverwrites)
            except discord.Forbidden:
                return await ctx.send("I do not have permission to block users!")

            await self.dbblocklist(member, channel, blockmsg, "block", reason)
            await self.bot.discordLogger.channelblock("block", member, ctx.author, channel, blockmsg, reason)
            await ctx.send(
                f"{member} has been blocked from viewing {channel.mention if isinstance(channel, discord.TextChannel) else channel.name}")
            return

        if flag_options.get('embed'):
            if await self.bot.db.fetchval(
                    "SELECT blocktype @> ARRAY['embedd'] FROM channel_block WHERE userid = $1 AND channelid = $2",
                    member.id, channel.id):
                return await ctx.send(f"{member} is already blocked from embedding to {channel.mention}")

            blockmsg.append("embedd")
            if not isinstance(channel, discord.VoiceChannel):
                try:
                    channeloverwrites = channel.overwrites_for(member)
                    channeloverwrites.embed_links = False
                    channeloverwrites.attach_files = False
                    await channel.set_permissions(member, overwrite=channeloverwrites)
                except discord.Forbidden:
                    return await ctx.send("I do not have permission to block users!")
            else:
                return await ctx.send("You cannot stop embedding in a voice channel")

        if flag_options.get('addreactions'):
            if await self.bot.db.fetchval(
                    "SELECT blocktype @> ARRAY['react'] FROM channel_block WHERE userid = $1 AND channelid = $2",
                    member.id, channel.id):
                return await ctx.send(f"{member} is already blocked from reacting in {channel.mention}")
            blockmsg.append("react")
            if not isinstance(channel, discord.VoiceChannel):
                try:
                    channeloverwrites = channel.overwrites_for(member)
                    channeloverwrites.add_reactions = False
                    await channel.set_permissions(member, overwrite=channeloverwrites)
                except discord.Forbidden:
                    return await ctx.send("I do not have permission to block users!")
            else:
                return await ctx.send("You cannot block reactions in a voice channel")

        if len(blockmsg) == 0:
            await ctx.send("Please use a flag for the permission you would like the block!")
            await ctx.send_help(ctx.command)
            return

        await self.dbblocklist(member, channel, blockmsg, "block", reason)
        await self.bot.discordLogger.channelblock("block", member, ctx.author, channel, blockmsg, reason)
        await ctx.send(
            f"{member} has been blocked from {'ing, '.join(blockmsg)}ing in {channel.mention if isinstance(channel, discord.TextChannel) else channel.name}")

    @commands.guild_only()
    @checks.is_staff_or_perms("Mod", manage_roles=True)
    @flags.add_flag("--view", '-v', action="store_true", default=False)
    @flags.add_flag("--embed", '-e', action="store_true", default=False)
    @flags.add_flag("--addreactions", '-a', action="store_true", default=False)
    @flags.add_flag("--channel", '-c', type=str, default=None)
    @flags.command()
    async def unblock(self, ctx, member: discord.Member, **flag_options):
        """Unblocks a user's permission in a channel (Mod+ or manage roles)"""
        modandbotprotection = await checks.modAndBotProtection(self.bot, ctx, member, "unblock")
        if modandbotprotection is not None:
            await ctx.send(modandbotprotection)
            return

        channel = flag_options.get('channel')
        if channel is None:
            channel = ctx.channel

        elif isinstance(channel, str):
            match = re.search(r'\d+', channel)
            cid = int(match.group()) if match is not None else channel
            channel = self.get_guild_channels(ctx.guild, cid)

        blockmsg = []
        if flag_options.get('view'):
            blockmsg.append("view")
            if not await self.bot.db.fetchval(
                    "SELECT blocktype @> ARRAY['view'] FROM channel_block WHERE userid = $1 AND channelid = $2",
                    member.id, channel.id):
                return await ctx.send(
                    f"{member} is not blocked from seeing {channel.mention if isinstance(channel, discord.TextChannel) else channel.name}")
            try:
                channeloverwrites = channel.overwrites_for(member)
                channeloverwrites.read_messages = None
                await channel.set_permissions(member, overwrite=channeloverwrites)
            except discord.Forbidden:
                return await ctx.send("I do not have permission to unblock users!")

        if flag_options.get('embed'):
            if not await self.bot.db.fetchval(
                    "SELECT blocktype @> ARRAY['embedd'] FROM channel_block WHERE userid = $1 AND channelid = $2",
                    member.id, channel.id):
                return await ctx.send(f"{member} is not blocked from embedding to {channel.mention}")

            blockmsg.append("embedd")
            try:
                channeloverwrites = channel.overwrites_for(member)
                channeloverwrites.embed_links = None
                channeloverwrites.attach_files = None
                await channel.set_permissions(member, overwrite=channeloverwrites)
            except discord.Forbidden:
                return await ctx.send("I do not have permission to block users!")

        if flag_options.get('addreactions'):
            if not await self.bot.db.fetchval(
                    "SELECT blocktype @> ARRAY['react'] FROM channel_block WHERE userid = $1 AND channelid = $2",
                    member.id, channel.id):
                return await ctx.send(f"{member} is not blocked from reacting in {channel.mention}")
            blockmsg.append("react")
            try:
                channeloverwrites = channel.overwrites_for(member)
                channeloverwrites.add_reactions = None
                await channel.set_permissions(member, overwrite=channeloverwrites)
            except discord.Forbidden:
                return await ctx.send("I do not have permission to block users!")

        if len(blockmsg) == 0:
            return await ctx.send("Please use a flag for the permission you would like the block!")

        await self.dbblocklist(member, channel, blockmsg, "unblock")
        await self.bot.discordLogger.channelblock("unblock", member, ctx.author, channel, blockmsg)
        if 'embedd' in blockmsg:
            idx = blockmsg.index('embedd')
            blockmsg[idx] = 'embed'

        await ctx.send(
            f"{member} has been unblocked and can now {', '.join(blockmsg)} in {channel.mention if isinstance(channel, discord.TextChannel) else channel.name}")

    @commands.command()
    async def listblocks(self, ctx, member: discord.Member = None):
        """Checks what channels you are blocked from, only staff may check other users"""
        if member is None:
            member = ctx.author
        has_perms = await checks.nondeco_is_staff_or_perms(ctx, "Mod", manage_roles=True)
        if not has_perms and member != ctx.author:
            return await ctx.send("You cannot check other people's restrictions!")

        # get data from database
        blocklist = []
        deletedchannelblocklist = []
        record = list(await self.bot.db.fetch(
            "SELECT blocktype, channelid, reason FROM channel_block WHERE userid = $1 AND guildid = $2", member.id,
            ctx.guild.id))
        if record is None or len(record) == 0:
            embed = discord.Embed(color=member.color.value)
            embed.set_author(name=f"Blocks for {member}", icon_url=member.avatar_url)
            embed.description = "There are none!"
            return await ctx.send(embed=embed)
        for blocktypes, channelid, reason in record:
            if not ctx.guild.get_channel(channelid):
                deletedchannelblocklist.append(dbBlocks(blocktypes, channelid, reason))
            else:
                blocklist.append(dbBlocks(blocktypes, ctx.guild.get_channel(channelid), reason))

        embed = discord.Embed(color=member.color.value)
        embed.set_author(name=f"Blocks for {member}:", icon_url=member.avatar_url)
        bmsg = ""
        for idx, block in enumerate(blocklist, start=1):
            bmsg += f"{idx}: Channel: {block.channel.mention if isinstance(block.channel, discord.TextChannel) else block.channel.name} Restriction(s): `{'ing, '.join(block.blocktypes)}ing`"
            if block.reason:
                bmsg += f" Reason: `{block.reason}`"
            bmsg += "\n\n"

        if deletedchannelblocklist:
            for block in deletedchannelblocklist:
                await self.bot.db.execute("DELETE FROM channel_block WHERE userid = $1 AND guildid = $2 AND channelid = $3", member.id, ctx.guild.id, block.channel)

        embed.description = bmsg

        await ctx.send(embed=embed)


class dbBlocks():

    def __init__(self, blocktypes: list,
                 channel: typing.Union[int, discord.TextChannel, discord.VoiceChannel, discord.CategoryChannel],
                 reason: str):
        self.blocktypes = blocktypes
        self.channel = channel
        self.reason = reason


def setup(bot):
    bot.add_cog(Block(bot))
