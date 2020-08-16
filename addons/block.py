import discord
from discord.ext import commands, flags
import typing
import re
from utils import checks, common


class Block(commands.Cog):
    """Block perms for users in desired channels"""

    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member):
        record = list(await self.bot.db.fetch(
            "SELECT blocktype, channelid, reason FROM channel_block WHERE userid = $1 AND guildid = $2", member.id,
            member.guild.id))
        if not record:
            return

        blocklist = []
        for blocktype, channelid, reason in record:
            if not member.guild.get_channel(channelid):
                continue
            blocklist.append(dbBlocks(blocktype, member.guild.get_channel(channelid), reason))

        channellist = []
        for block in blocklist:
            await self.apply_blocks(member, block.channel, block.blocktypes)
            if block.channel not in channellist:
                channellist.append(block.channel.name)

        await self.bot.discordLogger.onjoinblock(member, channellist, await self.listblocksdb(member))

    async def apply_blocks(self, member: discord.Member, channel: typing.Union[
        discord.TextChannel, discord.VoiceChannel, discord.CategoryChannel], blocklist):
        """Applies blocks to a user on join"""
        perm_kwargs = {
            'view': {
                'read_messages': False
            },
            'embed': {
                'embed_links': False,
                'attach_files': False
            },
            'react': {
                'add_reactions': False
            }
        }
        for block in blocklist:
            try:
                channeloverwrites = channel.overwrites_for(member)
                channeloverwrites.update(**perm_kwargs[block])
                await channel.set_permissions(member, overwrite=channeloverwrites)
            except discord.Forbidden:
                pass


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
        blockmsg = set()

        perm_kwargs = {
            'view': {
                'read_messages': False
            },
            'embed': {
                'embed_links': False,
                'attach_files': False
            },
            'react': {
                'add_reactions': False
            }
        }
        if flag_options.get('view'):
            blockmsg.add('view')

        if flag_options.get('embed'):
            blockmsg.add('embed')

        if flag_options.get('addreactions'):
            blockmsg.add('react')

        if len(blockmsg) == 0:
            await ctx.send("Please use a flag for the permission you would like the block!")
            await ctx.send_help(ctx.command)
            return

        alreadyblocked = set()
        for blocktype in blockmsg:
            if await self.bot.db.fetchval(
                    f"SELECT blocktype @> ARRAY['{blocktype}'] FROM channel_block WHERE userid = $1 AND channelid = $2",
                    member.id, channel.id):
                alreadyblocked.add(blocktype)
                continue
            try:
                channeloverwrites = channel.overwrites_for(member)
                channeloverwrites.update(**perm_kwargs[blocktype])
                await channel.set_permissions(member, overwrite=channeloverwrites)
            except discord.Forbidden:
                return await ctx.send("I do not have permission to block users!")

        if alreadyblocked:
            await ctx.send(
                f"{member} is already blocked from being able to `{'`, `'.join(alreadyblocked)}` in {channel.mention if isinstance(channel, discord.TextChannel) else channel.name}")
            blockmsg -= alreadyblocked

        if len(blockmsg) > 0:
            await self.dbblocklist(member, channel, blockmsg, "block", reason)
            await self.bot.discordLogger.channelblock("block", member, ctx.author, channel, blockmsg, reason)
            await ctx.send(
                f"{member} can no longer `{'`, `'.join(blockmsg)}` in {channel.mention if isinstance(channel, discord.TextChannel) else channel.name}.")

    @commands.guild_only()
    @checks.is_staff_or_perms("Mod", manage_roles=True)
    @flags.add_flag("--view", '-v', action="store_true", default=False)
    @flags.add_flag("--embed", '-e', action="store_true", default=False)
    @flags.add_flag("--addreactions", '-a', action="store_true", default=False)
    @flags.add_flag("--channel", '-c', type=str, default=None)
    @flags.command()
    async def unblock(self, ctx, member: discord.Member, **flag_options):
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

        unblockmsg = set()

        perm_kwargs = {
            'view': {
                'read_messages': None
            },
            'embed': {
                'embed_links': None,
                'attach_files': None
            },
            'react': {
                'add_reactions': None
            }
        }
        if flag_options.get('view'):
            unblockmsg.add('view')

        if flag_options.get('embed'):
            unblockmsg.add('embed')

        if flag_options.get('addreactions'):
            unblockmsg.add('react')

        if len(unblockmsg) == 0:
            await ctx.send("Please use a flag for the permission you would like the unblock!")
            await ctx.send_help(ctx.command)
            return

        notblocked = set()
        for unblocktype in unblockmsg:
            if not await self.bot.db.fetchval(
                    f"SELECT blocktype @> ARRAY['{unblocktype}'] FROM channel_block WHERE userid = $1 AND channelid = $2",
                    member.id, channel.id):
                notblocked.add(unblocktype)
                continue
            try:
                channeloverwrites = channel.overwrites_for(member)
                channeloverwrites.update(**perm_kwargs[unblocktype])
                await channel.set_permissions(member, overwrite=channeloverwrites)
                if channeloverwrites.is_empty():
                    await channel.set_permissions(member, overwrite=None)
            except discord.Forbidden:
                return await ctx.send("I do not have permission to unblock users!")

        if notblocked:
            await ctx.send(
                f"{member} is not blocked from being able to `{'`, `'.join(notblocked)}` in {channel.mention if isinstance(channel, discord.TextChannel) else channel.name}")
            unblockmsg -= notblocked

        if len(unblockmsg) > 0:
            await self.dbblocklist(member, channel, unblockmsg, "unblock")
            await self.bot.discordLogger.channelblock("unblock", member, ctx.author, channel, unblockmsg)
            await ctx.send(
                f"{member} can `{'`, `'.join(unblockmsg)}` in {channel.mention if isinstance(channel, discord.TextChannel) else channel.name} again.")

    @checks.is_staff_or_perms('Mod', manage_roles=True)
    @commands.command()
    async def unblockall(self, ctx, member: discord.Member):
        """Removes all blocks on a user (Mod+, manage roles)"""
        channelids = await self.bot.db.fetch(
            "SELECT channelid FROM channel_block WHERE userid = $1 AND guildid = $2", member.id,
            member.guild.id)
        if not channelids:
            return await ctx.send("No blocks found for this user!")

        channellist = []
        for channelid in channelids:
            channelid = channelid[0]
            if ctx.guild.get_channel(channelid) is None:
                continue
            channel = ctx.guild.get_channel(channelid)
            try:
                await channel.set_permissions(member, overwrite=None)
            except discord.Forbidden:
                pass

            if channel not in channellist:
                channellist.append(channel.name)

        await self.bot.db.execute("DELETE FROM channel_block WHERE guildid = $1 AND userid = $2", member.guild.id,
                                  member.id)
        await ctx.send(f"All blocks cleared for {member}")

        await self.bot.discordLogger.unblockalllog(member, ctx.author, channellist)

    async def listblocksdb(self, member) -> discord.Embed or None:
        blocklist = []
        deletedchannelblocklist = []
        record = list(await self.bot.db.fetch(
            "SELECT blocktype, channelid, reason FROM channel_block WHERE userid = $1 AND guildid = $2", member.id,
            member.guild.id))
        if record is None or len(record) == 0:
            return None
        for blocktypes, channelid, reason in record:
            if not member.guild.get_channel(channelid):
                deletedchannelblocklist.append(dbBlocks(blocktypes, channelid, reason))
            else:
                blocklist.append(dbBlocks(blocktypes, member.guild.get_channel(channelid), reason))

        embed = discord.Embed(color=member.color.value)
        embed.set_author(name=f"Blocks for {member}:", icon_url=member.avatar_url)
        bmsg = ""
        for idx, block in enumerate(blocklist, start=1):
            bmsg += f"{idx}: Channel: {block.channel.mention if isinstance(block.channel, discord.TextChannel) else block.channel.name} Restriction(s): `{', '.join(block.blocktypes)}`"
            if block.reason:
                bmsg += f" Reason: `{block.reason}`"
            bmsg += "\n\n"

        if deletedchannelblocklist:
            for block in deletedchannelblocklist:
                await self.bot.db.execute(
                    "DELETE FROM channel_block WHERE userid = $1 AND guildid = $2 AND channelid = $3", member.id,
                    member.guild.id, block.channel)

        embed.description = bmsg
        return embed

    @commands.command()
    async def listblocks(self, ctx, member: discord.Member = None):
        """Checks what channels you are blocked from, only staff may check other users"""
        if member is None:
            member = ctx.author
        has_perms = await checks.nondeco_is_staff_or_perms(ctx, "Mod", manage_roles=True)
        if not has_perms and member != ctx.author:
            return await ctx.send("You cannot check other people's restrictions!")

        # get data from database
        embed = await self.listblocksdb(member)
        if not embed:
            embed = discord.Embed(color=member.color.value)
            embed.set_author(name=f"Blocks for {member}", icon_url=member.avatar_url)
            embed.description = "There are none!"
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
