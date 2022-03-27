import discord
from discord.ext import commands, flags
import typing
import re
from utils import checks, errors


async def apply_blocks(member: discord.Member, channel: typing.Union[
    discord.TextChannel, discord.VoiceChannel, discord.CategoryChannel], block_list):
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
    for block in block_list:
        try:
            channel_overwrites = channel.overwrites_for(member)
            channel_overwrites.update(**perm_kwargs[block])
            await channel.set_permissions(member, overwrite=channel_overwrites)
        except discord.Forbidden:
            pass


class Block(commands.Cog):
    """Block perms for users in desired channels"""

    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        record = list(await self.bot.db.fetch(
            "SELECT block_type, channel_id, reason FROM channel_block WHERE user_id = $1 AND guild_id = $2", member.id,
            member.guild.id))
        if not record:
            return

        block_list = []
        for block_type, channel_id, reason in record:
            if not member.guild.get_channel(channel_id):
                continue
            block_list.append(DbBlocks(block_type, member.guild.get_channel(channel_id), reason))

        channel_list = []
        for block in block_list:
            await apply_blocks(member, block.channel, block.block_types)
            if block.channel not in channel_list:
                channel_list.append(block.channel.name)

        await self.bot.terrygon_logger.on_join_block(member, channel_list, await self.list_blocks_db(member))

    async def db_block_list(self, member: discord.Member,
                            channel: typing.Union[discord.TextChannel, discord.VoiceChannel, discord.CategoryChannel],
                            blocktypes, mode, reason: str = None):
        """Adds a block to the db entry"""
        if mode == "block":
            async with self.bot.db.acquire() as conn:
                if not await conn.fetchval(
                        "SELECT user_id FROM channel_block WHERE user_id = $1 AND guild_id = $2 AND channel_id = $3",
                        member.id,
                        member.guild.id, channel.id):
                    await conn.execute(
                        "INSERT INTO channel_block (user_id, guild_id, channel_id, block_type, reason) VALUES ($1, $2, $3, $4, $5)",
                        member.id, member.guild.id, channel.id, blocktypes, reason)
                else:
                    await conn.execute(
                        "UPDATE channel_block SET block_type = array_cat(block_type, $1) WHERE user_id = $2 AND channel_id = $3",
                        blocktypes, member.id, channel.id)

        elif mode == "unblock":
            async with self.bot.db.acquire() as conn:
                if not await conn.fetchval("SELECT user_id FROM channel_block WHERE user_id = $1 AND channel_id = $2",
                                           member.id, channel.id):
                    return False

                for b in blocktypes:
                    await conn.execute(
                        "UPDATE channel_block SET block_type = array_remove(block_type, $1) WHERE user_id = $2 AND channel_id = $3",
                        b, member.id, channel.id)
                    if not await conn.fetchval(
                            "SELECT block_type FROM channel_block WHERE user_id = $1 AND channel_id = $2", member.id,
                            channel.id):
                        await conn.execute("DELETE FROM channel_block WHERE user_id = $1 AND channel_id = $2", member.id,
                                           channel.id)
                        break

                return True

    def get_guild_channels(self, guild: discord.Guild, channel_data: typing.Union[str, int]):
        """Tries to match an id with a channel's guilds"""
        if isinstance(channel_data, int) and channel_data in (c.id for c in guild.channels):
            return guild.get_channel(channel_data)
        elif isinstance(channel_data, str):
            return discord.utils.get(guild.channels, name=channel_data)
        else:
            raise commands.BadArgument("Invalid channel id")

    @commands.guild_only()
    @checks.is_staff_or_perms("Mod", manage_roles=True)
    @flags.add_flag("--embed", '-e', action="store_true", default=False)
    @flags.add_flag("--addreactions", '-a', action="store_true", default=False)
    @flags.add_flag('--view', '-v', action='store_true', default=False)
    @flags.add_flag("--channel", '-c', default=None)
    @flags.add_flag("--reason", '-r', type=str, default="", nargs="+")
    @flags.command()
    async def block(self, ctx: commands.Context, member: discord.Member, **flag_options):
        """
        Blocks a user's permission in a channel (Mod+ or manage roles)

        This command can be used to block a user from having certain permissions in specific channels or channel categories.
        Please note that if you block someone from a category it will only be applied to the channels that are synced with the category
        If no permission flags are specified, it will automatically block viewing

        **FLAGS:**
        Optional:
        `-c` or `--channel` arguments: `<channel>` This flag is used to tell the bot what channel (voice, text, category) you are blocking the user from. If not specified, it will block in the channel the command is ran in.
        `-v` or `--view` This flag is used to block the user from viewing the channel. (If no other permission flag is used, this is the default option)
        `-e` or `--embed` This flag is used to block the user from embedding links or attaching files in the channel.
        `-a` or `--addreactions` This flag is used to block the user from reacting in the channel.
        `-r` or `--reason` arguments: `[reason]...` This flag is used to specify a reason for blocking the user, please note that this flag must be the final one used as it will read everything after it as apart of the reason.
        """
        mod_bot_protection = await checks.mod_bot_protection(self.bot, ctx, member, "block")
        if mod_bot_protection is not None:
            await ctx.send(mod_bot_protection)
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
        block_list = set()

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
        if (not flag_options.get('embed') and not flag_options.get('addreactions')) or flag_options.get('view'):
            block_list.add('view')

        if flag_options.get('embed'):
            block_list.add('embed')

        if flag_options.get('addreactions'):
            block_list.add('react')

        if len(block_list) == 0:
            # this should never trigger
            await ctx.send("Please use a flag for the permission you would like the block!")
            await ctx.send_help(ctx.command)
            return

        already_blocked = set()
        for block_type in block_list:
            if await self.bot.db.fetchval(
                    f"SELECT block_type @> ARRAY['{block_type}'] FROM channel_block WHERE user_id = $1 AND channel_id = $2",
                    member.id, channel.id):
                already_blocked.add(block_type)
                continue
            try:
                channel_overwrites = channel.overwrites_for(member)
                channel_overwrites.update(**perm_kwargs[block_type])
                await channel.set_permissions(member, overwrite=channel_overwrites)
            except discord.Forbidden:
                return await ctx.send("I do not have permission to block users!")

        if already_blocked:
            await ctx.send(
                f"{member} is already blocked from being able to `{'`, `'.join(already_blocked)}` in {channel.mention if isinstance(channel, discord.TextChannel) else channel.name}")
            block_list -= already_blocked

        if len(block_list) > 0:
            await self.db_block_list(member, channel, block_list, "block", reason)
            try:
                await member.send(f"You have been blocked from being able to `{', '.join(block_list)}` in {channel}. on {channel.guild.name}")
            except discord.Forbidden:
                pass

            try:
                await self.bot.terrygon_logger.channel_block("block", member, ctx.author, channel, block_list, reason)
            except errors.LoggingError:
                pass
            await ctx.send(
                f"{member} can no longer `{'`, `'.join(block_list)}` in {channel.mention if isinstance(channel, discord.TextChannel) else channel.name}.")

    @commands.guild_only()
    @checks.is_staff_or_perms("Mod", manage_roles=True)
    @flags.add_flag("--view", '-v', action="store_true", default=False)
    @flags.add_flag("--embed", '-e', action="store_true", default=False)
    @flags.add_flag("--addreactions", '-a', action="store_true", default=False)
    @flags.add_flag("--channel", '-c', type=str, default=None)
    @flags.command()
    async def unblock(self, ctx: commands.Context, member: discord.Member, **flag_options):
        """
        Unblocks a user from  a channel.

        **FLAGS:**
        Optional:
        `-c` or `--channel` arguments: `<channel>` description: This flag is used to tell the bot what channel (voice, text, category) you are blocking the user from. If not specified, it will unblock in the channel the command is ran in.
        `-v` or `--view` This flag is used to unblock the user from viewing the channel. (If no other permission flag is used, this is the default option)
        `-e` or `--embed` This flag is used to unblock the user from embedding links or attaching files in the channel.
        `-a` or `--addreactions` This flag is used to unblock the user from reacting in the channel.
        """

        channel = flag_options.get('channel')
        if channel is None:
            channel = ctx.channel

        elif isinstance(channel, str):
            match = re.search(r'\d+', channel)
            cid = int(match.group()) if match is not None else channel
            channel = self.get_guild_channels(ctx.guild, cid)

        unblock_list = set()

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
        if (not flag_options.get('embed') and not flag_options.get('addreactions')) or flag_options.get('view'):
            unblock_list.add('view')

        if flag_options.get('embed'):
            unblock_list.add('embed')

        if flag_options.get('addreactions'):
            unblock_list.add('react')

        if len(unblock_list) == 0:
            await ctx.send("Please use a flag for the permission you would like the unblock!")
            await ctx.send_help(ctx.command)
            return

        not_blocked = set()
        for unblock_type in unblock_list:
            if not await self.bot.db.fetchval(
                    f"SELECT block_type @> ARRAY['{unblock_type}'] FROM channel_block WHERE user_id = $1 AND channel_id = $2",
                    member.id, channel.id):
                not_blocked.add(unblock_type)
                continue
            try:
                channel_overwrites = channel.overwrites_for(member)
                channel_overwrites.update(**perm_kwargs[unblock_type])
                await channel.set_permissions(member, overwrite=channel_overwrites)
                if channel_overwrites.is_empty():
                    await channel.set_permissions(member, overwrite=None)
            except discord.Forbidden:
                return await ctx.send("I do not have permission to unblock users!")

        if not_blocked:
            await ctx.send(
                f"{member} is not blocked from being able to `{'`, `'.join(not_blocked)}` in {channel.mention if isinstance(channel, discord.TextChannel) else channel.name}")
            unblock_list -= not_blocked

        if len(unblock_list) > 0:
            await self.db_block_list(member, channel, unblock_list, "unblock")
            try:
                await member.send(f"You have been unblocked and are now able to `{', '.join(unblock_list)}` in {channel.mention}. on {channel.guild.name}")
            except discord.Forbidden:
                pass

            try:
                await self.bot.terrygon_logger.channel_block("unblock", member, ctx.author, channel, unblock_list)
            except errors.LoggingError:
                pass

            await ctx.send(
                f"{member} can `{'`, `'.join(unblock_list)}` in {channel.mention if isinstance(channel, discord.TextChannel) else channel.name} again.")

    @commands.guild_only()
    @checks.is_staff_or_perms('Mod', manage_roles=True)
    @commands.command(name="unblockall")
    async def unblock_all(self, ctx: commands.Context, member: discord.Member):
        """Removes all blocks on a user (Mod+, manage roles)"""
        channel_ids = await self.bot.db.fetch(
            "SELECT channel_id FROM channel_block WHERE user_id = $1 AND guild_id = $2", member.id,
            member.guild.id)
        if not channel_ids:
            return await ctx.send("No blocks found for this user!")

        channel_list = []
        for channel_id in channel_ids:
            channel_id = channel_id[0]
            if ctx.guild.get_channel(channel_id) is None:
                continue
            channel = ctx.guild.get_channel(channel_id)
            try:
                await channel.set_permissions(member, overwrite=None)
            except discord.Forbidden:
                pass

            if channel not in channel_list:
                channel_list.append(channel.name)

        await self.bot.db.execute("DELETE FROM channel_block WHERE guild_id = $1 AND user_id = $2", member.guild.id,
                                  member.id)
        await ctx.send(f"All blocks cleared for {member}")

        try:
            await member.send(f"All blocks have been removed for you in on {ctx.guild.name}")
        except discord.Forbidden:
            pass

        await self.bot.terrygon_logger.unblock_all_log(member, ctx.author, channel_list)

    async def list_blocks_db(self, member: discord.Member) -> discord.Embed or None:
        block_list = []
        deleted_channel_block_list = []
        record = list(await self.bot.db.fetch(
            "SELECT block_type, channel_id, reason FROM channel_block WHERE user_id = $1 AND guild_id = $2", member.id,
            member.guild.id))
        if record is None or len(record) == 0:
            return None
        for block_types, channel_id, reason in record:
            if not member.guild.get_channel(channel_id):
                deleted_channel_block_list.append(DbBlocks(block_types, channel_id, reason))
            else:
                block_list.append(DbBlocks(block_types, member.guild.get_channel(channel_id), reason))

        embed = discord.Embed(color=member.color.value)
        embed.set_author(name=f"Blocks for {member}:", icon_url=member.avatar_url)
        bmsg = ""
        for idx, block in enumerate(block_list, start=1):
            bmsg += f"{idx}: Channel: {block.channel.mention if isinstance(block.channel, discord.TextChannel) else block.channel.name} Restriction(s): `{', '.join(block.block_types)}`"
            if block.reason:
                bmsg += f" Reason: `{block.reason}`"
            bmsg += "\n\n"

        if deleted_channel_block_list:
            for block in deleted_channel_block_list:
                await self.bot.db.execute(
                    "DELETE FROM channel_block WHERE user_id = $1 AND guild_id = $2 AND channel_id = $3", member.id,
                    member.guild.id, block.channel)

        embed.description = bmsg
        return embed

    @commands.guild_only()
    @commands.command(name="listblocks", aliases=['listblock'])
    async def list_blocks(self, ctx: commands.Context, member: discord.Member = None):
        """Checks what channels you are blocked from, only staff may check other users"""
        if member is None:
            member = ctx.author
        has_perms = await checks.nondeco_is_staff_or_perms(ctx, self.bot.db, "Mod", manage_roles=True)
        if not has_perms and member != ctx.author:
            return await ctx.send("You cannot check other people's restrictions!")

        # get data from database
        embed = await self.list_blocks_db(member)
        if not embed:
            embed = discord.Embed(color=member.color.value)
            embed.set_author(name=f"Blocks for {member}", icon_url=member.avatar_url)
            embed.description = "There are none!"
        await ctx.send(embed=embed)


class DbBlocks:

    def __init__(self, block_types: list,
                 channel: typing.Union[int, discord.TextChannel, discord.VoiceChannel, discord.CategoryChannel],
                 reason: str):
        self.block_types = block_types
        self.channel = channel
        self.reason = reason


async def setup(bot):
    await bot.add_cog(Block(bot))
