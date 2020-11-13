import discord
from discord.ext import commands, flags
from main import read_config
from utils import checks, errors, common, paginator
import typing
import logzero
from logzero import logger as console_logger

logzero.logfile("logs/setupcog.log", maxBytes=1e6)


class Setup(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    async def get_db_asset(self, asset: str, guild: discord.Guild):
        async with self.bot.db.acquire() as conn:
            if asset in ('modrole', 'adminrole', 'ownerrole', 'approvedrole', 'mutedrole'):
                return (await conn.fetchrow(f"SELECT {asset} FROM roles WHERE guildid = $1", guild.id))[0]

            elif asset in ('modlogs', 'messagelogs', 'memberlogs', 'auditlogs'):
                return (await conn.fetchrow(f"SELECT {asset} FROM log_channels WHERE guildid = $1", guild.id))[0]

            else:
                console_logger.error("Invalid input given for asset")
                return None

    async def set_unset_role(self, ctx, role: discord.Role, role_type, mode):
        if not isinstance(role, discord.Role) and role is not None:
            await ctx.send("Invalid role given! Does this role exist?")
            return

        if role_type not in ('modrole', 'adminrole', 'ownerrole', 'approvedrole', 'mutedrole'):
            raise commands.BadArgument("Invalid Database Role")

        async with self.bot.db.acquire() as conn:

            if mode == 'unset':
                role_id = await self.get_db_asset(role_type, ctx.guild)
                if role_id is None:
                    return -1
                try:
                    role = ctx.guild.get_role(role_id)
                    if not role:
                        raise errors.loggingError("Deleted role", ctx.guild)
                    await self.bot.discord_logger.log_setup("unset", f"{role_type} role", ctx.author,
                                                            role, 'modlogs')
                except errors.loggingError:
                    console_logger.warning(f"Failed to log {role_type} database unset on server {ctx.guild.name}.")
                await conn.execute(f"UPDATE roles SET {role_type} = NULL WHERE guildid = $1", ctx.guild.id)
                return 0

            else:
                # just in case!
                if role is None:
                    return -1

                await conn.execute(f"UPDATE roles SET {role_type} = $1 WHERE guildid = $2", role.id, ctx.guild.id)
                try:
                    await self.bot.discord_logger.log_setup("set", f"{role_type} role", ctx.author,
                                                            await self.get_db_asset(role_type,
                                                                                    ctx.guild) if role is None else ctx.guild.get_role(
                                                                role.id), 'modlogs')
                except errors.loggingError:
                    console_logger.warning(f"Failed to log {role_type} database set! on server {ctx.guild.name}")

                return 0

    async def set_unset_channels(self, ctx, channel: typing.Union[discord.TextChannel, None], channel_type, mode):
        """Sets a log channel to the database, mode should be either `set` or `unset`"""
        if not isinstance(channel, discord.TextChannel) and channel is not None:
            await ctx.send("Invalid channel, does this channel exist?")
            return

        if channel_type not in ('modlogs', 'messagelogs', 'memberlogs', 'auditlogs'):
            raise commands.BadArgument("Invalid Database Channel")

        async with self.bot.db.acquire() as conn:
            if mode.lower() == 'unset':
                try:
                    channel_id = await self.get_db_asset(channel_type, ctx.guild)
                    if channel_id is None:
                        return -1

                    await self.bot.discord_logger.log_setup("unset", f"{channel_type} channel", ctx.author,
                                                            self.bot.get_channel(channel_id), channel_type)

                except errors.loggingError:
                    console_logger.warning(f"Failed log setting the {channel} log channel on server: {ctx.guild.name}")

                await conn.execute(f"UPDATE log_channels SET {channel_type} = NULL WHERE guildid = $1", ctx.guild.id)
                return 0

            elif mode.lower() == 'set':
                # just in case
                if channel is None:
                    await ctx.send("Please enter a channel to set")
                    return -1

                await conn.execute(f"UPDATE log_channels SET {channel_type} = $1 WHERE guildid = $2", channel.id,
                                   ctx.guild.id)

                try:
                    await self.bot.discord_logger.log_setup("set", f"{channel_type} channel", ctx.author, channel,
                                                            channel_type)
                except errors.loggingError:
                    console_logger.warning(f"Failed log setting the {channel} log channel on server: {ctx.guild.name}")

                return 0

            else:
                raise commands.BadArgument("Unknown mode, valid modes are set and unset!")

    # channels
    @commands.guild_only()
    @checks.is_staff_or_perms("Owner", administrator=True)
    @commands.group(invoke_without_command=True)
    async def logchannel(self, ctx):
        """Command for setting and unsetting log channels (Owner or administrator)"""
        await ctx.send_help(ctx.command)

    @commands.guild_only()
    @checks.is_staff_or_perms("Owner", administrator=True)
    @flags.add_flag("--modlogs", type=discord.TextChannel)
    @flags.add_flag("--memberlogs", type=discord.TextChannel)
    @flags.add_flag("--messagelogs", type=discord.TextChannel)
    @logchannel.command(cls=flags.FlagCommand, aliases=['set'])
    async def channelset(self, ctx, **log_channels):
        """Sets a channel to be used as a log channel (Owner or administrator)

        **Flags:**
        One or more of:
        - `--modlogs` arguments: `<channel>` logs moderaton commands like warn/ban/mute/kick/lockdown
        - `--memberlogs` arguments: `<channel>` logs all data relating to users being updated, like nickname changes or role changes
        - `--messagelogs` arguments: `<channel>` logs all data relating to messages, such as edits, deletions, or pinned messages by trusted members
        """
        active_flags = {l for l in log_channels.items() if l[1]}
        if not active_flags:
            return await ctx.send(
                "Please specify a logchannel type you would like to add, flags are `--modlogs`, `--memberlogs`, and `--messagelogs`")

        else:
            msg = ""
            async with ctx.channel.typing():
                for channel_type, channel in active_flags:
                    if await self.set_unset_channels(ctx, channel, channel_type, 'set') == 0:
                        msg += f"{channel_type.title()}, "

            if msg:
                await ctx.send(msg.rstrip(", ") + " have been set!")
            else:
                # should never appear
                await ctx.send("Unable to set any channels to the database!")

    @commands.guild_only()
    @checks.is_staff_or_perms("Owner", administrator=True)
    @flags.add_flag("--modlogs", default=None, action="store_true")
    @flags.add_flag("--memberlogs", default=None, action="store_true")
    @flags.add_flag("--messagelogs", default=None, action="store_true")
    @logchannel.command(cls=flags.FlagCommand, aliases=['unset'])
    async def channelunset(self, ctx, **channel_type):
        """
        Unsets a log channel (Owner or administrator)

        **Flags:**
        One or more of:
        - `--modlogs` Unsets the mod logs channel.
        - `--memberlogs` Unsets the member logs channel.
        - `--messagelogs` Unsets the message logs channel.
        """
        active_flags = [l[0] for l in channel_type.items() if l[1]]
        if not active_flags:
            await ctx.send("Please specify a logchannel type you would like to remove, flags are `--modlogs`, `--memberlogs`, and `--messagelogs`")
        else:
            msg = ""
            async with ctx.channel.typing():
                for logtype in active_flags:
                    if await self.set_unset_channels(ctx, None, logtype, 'unset') == 0:
                        msg += f"{logtype.title()}, "

            if msg:
                await ctx.send(msg.rstrip(", ") + " have been unset!")
            else:
                # should never appear
                await ctx.send("Unable to unset any channels to the database!")

    # roles
    @commands.guild_only()
    @checks.is_staff_or_perms("Owner", administrator=True)
    @commands.group(invoke_without_command=True, aliases=['serverrole', 'dbrole'], name="staffrole")
    async def staff_role(self, ctx):
        """Command for setting and unsetting staff roles (Owner or administrator)"""
        await ctx.send_help(ctx.command)

    @checks.is_staff_or_perms("Owner", administrator=True)
    @flags.add_flag("--adminrole", type=discord.Role)
    @flags.add_flag("--modrole", type=discord.Role)
    @flags.add_flag("--ownerrole", type=discord.Role)
    @staff_role.command(cls=flags.FlagCommand, name="set")
    async def staff_role_set(self, ctx, **role_flags):
        """Sets a staff role to be used in the database (Owner or administrator)

        **Flags:**
        One or more
        - `--adminrole` arguments: `<role>` Role for administrators.
        - `--ownerrole` arguments: `<role>` Role for owners.
        - `--modrole` arguments: `<role>` Role for moderators
        """
        active_flags = {l for l in role_flags.items() if l[1]}
        if not active_flags:
            return await ctx.send(
                "Please specify a database role you would like to add, flags are `--adminrole`, `--modrole`, and `--ownerrole`")
        else:
            msg = ""
            async with ctx.channel.typing():
                for role_type, role in active_flags:
                    if await self.set_unset_role(ctx, role, role_type, 'set') == 0:
                        msg += f"{role_type.title()}, "

            if msg:
                await ctx.send(msg.rstrip(", ") + " have been set!")
            else:
                await ctx.send("Unable to set any roles to the database!")

    @commands.guild_only()
    @checks.is_staff_or_perms("Owner", administrator=True)
    @flags.add_flag("--adminrole", default=None, action="store_true")
    @flags.add_flag("--modrole", default=None, action="store_true")
    @flags.add_flag("--ownerrole", default=None, action="store_true")
    @staff_role.command(cls=flags.FlagCommand, name="unset")
    async def role_unset(self, ctx, **role_flags):
        """Unsets a staff role (Owner or administrator)

        **Flags:**
        One or more
        - `--adminrole` Unsets the admin role
        - `--ownerrole` Unsets the owner role
        - `--modrole` Unsets the mod role
        """
        active_flags = {l for l in role_flags.items() if l[1]}
        if not active_flags:
            return await ctx.send(
                "Please specify a database role you would like to add, flags are `--adminrole`, `--modrole`, and `--ownerrole`")
        else:
            msg = ""
            async with ctx.channel.typing():
                for role_type, role in active_flags:
                    if await self.set_unset_role(ctx, None, role_type, 'unset') == 0:
                        msg += f"{role_type.title()}, "

            if msg:
                await ctx.send(msg.rstrip(", ") + " have been unset!")
            else:
                # should never appear
                await ctx.send("Unable to unset any roles to the database!")

    async def toggle_join_logs(self, ctx):
        async with self.bot.db.acquire() as conn:
            member_logs_channel_id = await conn.fetchval("SELECT memberlogs FROM log_channels WHERE guildid =  $1",
                                                      ctx.guild.id)
            if member_logs_channel_id is None:
                await ctx.send("Member log channel not configured!")
                return

            if await conn.fetchval("SELECT enablejoinleavelogs FROM guild_settings WHERE guildid = $1", ctx.guild.id):
                await conn.execute("UPDATE guild_settings SET enablejoinleavelogs = FALSE WHERE guildid = $1",
                                   ctx.guild.id)
                await ctx.send("Join and leave logs are now off!")
                await self.bot.discord_logger.toggle_log_setup("unset", "join leave logs", ctx.author, 'memberlogs')
            else:
                await conn.execute("UPDATE guild_settings SET enablejoinleavelogs = TRUE WHERE guildid = $1",
                                   ctx.guild.id)
                await ctx.send("Join and leave logs are now on!")
                await self.bot.discord_logger.toggle_log_setup("set", "join leave logs", ctx.author, 'memberlogs')

    async def toggle_core_message_logs(self, ctx):
        async with self.bot.db.acquire() as conn:
            member_logs_channel_id = await conn.fetchval("SELECT messagelogs FROM log_channels WHERE guildid =  $1",
                                                      ctx.guild.id)
            if member_logs_channel_id is None:
                await ctx.send("Message log channel not configured!")
                return

            if await conn.fetchval("SELECT enableCoreMessageLogs FROM guild_settings WHERE guildid = $1", ctx.guild.id):
                await conn.execute("UPDATE guild_settings SET enableCoreMessageLogs = FALSE WHERE guildid = $1",
                                   ctx.guild.id)
                await ctx.send("Message edits and deletes are no longer logged!")
                await self.bot.discord_logger.toggle_log_setup("unset", "core message logs", ctx.author, 'messagelogs')
            else:
                await conn.execute("UPDATE guild_settings SET enableCoreMessageLogs = TRUE WHERE guildid = $1",
                                   ctx.guild.id)
                await ctx.send("Message edits and deletes are now being logged!")
                await self.bot.discord_logger.toggle_log_setup("set", "core message logs", ctx.author, 'messagelogs')

    @commands.guild_only()
    @checks.is_staff_or_perms('Owner', administrator=True)
    @commands.group(invoke_without_command=True)
    async def logs(self, ctx):
        """Command used to manage all logging systems. You can set and unset channels, modroles, and toggle which things you would like to log for your server"""
        await ctx.send_help(ctx.command)

    @commands.guild_only()
    @checks.is_staff_or_perms('Owner', administrator=True)
    @logs.command(name='joinleave')
    async def join_leave(self, ctx):
        """Enables or disables joining and leaving logs"""
        await self.toggle_join_logs(ctx)

    @commands.guild_only()
    @checks.is_staff_or_perms('Owner', administrator=True)
    @logs.command(name="editsdeletes", aliases=['coremessagelogs'])
    async def edits_and_deletes(self, ctx):
        """Enables or disables message edits or deletions"""
        await self.toggle_core_message_logs(ctx)

    @commands.guild_only()
    @checks.is_staff_or_perms('Mod', manage_roles=True)
    @commands.group(invoke_without_command=True, name="mutedrole")
    async def muted_role(self, ctx):
        """Manage muted role"""
        await ctx.send_help(ctx.command)

    @commands.guild_only()
    @checks.is_staff_or_perms('Mod', manage_roles=True)
    @muted_role.command(name="set")
    async def muted_role_set(self, ctx, role: discord.Role = None):
        """Sets and configures a server's muted role"""
        out = await self.muted_role_setup(ctx, role)
        if out:
            await ctx.send(out)

    @commands.guild_only()
    @checks.is_staff_or_perms('Admin', manage_guild=True)
    @muted_role.command(name="unset")
    async def muted_role_unset(self, ctx):
        """Unsets the muted role (Admin+, manage server)"""
        muted_role_id = await self.bot.db.fetchval("SELECT mutedrole FROM roles WHERE guildid = $1", ctx.guild.id)
        if not muted_role_id:
            return await ctx.send("No mutedrole saved in the database.")
        await self.set_unset_role(ctx, None, 'mutedrole', 'unset')
        res, msg = await paginator.YesNoMenu("Muted role, unset, would you like to delete it?").prompt(ctx)
        if res:
            try:
                await ctx.guild.get_role(muted_role_id).delete()
                await msg.edit(content="Role deleted!")
            except discord.Forbidden:
                return await msg.edit(content="I cannot delete roles!")
        else:
            await msg.edit(content="Role not deleted.")

    async def muted_role_setup(self, ctx, role: discord.Role = None):
        """Sets the muted role and configures the server to use the muted role."""
        if role is None:
            res, msg = await paginator.YesNoMenu("No muted role detected, would you like to create one?").prompt(ctx)
            if res:
                try:
                    role = await ctx.guild.create_role(name='Muted', reason="New role for muting members")
                except discord.Forbidden:
                    return "I am unable to create roles, please check permissions!"
                await msg.edit(
                    content="New role named `Muted` created, added to the database, and set up with all the channels")
            else:
                return await msg.edit(content="Canceled")
        else:
            await ctx.send("Muted role set!")

        # first go thru the categories
        try:
            for category in ctx.guild.categories:
                await category.set_permissions(role, send_messages=False, connect=False)

            # next the remaining channels
            for tc in ctx.guild.text_channels:
                if not tc.permissions_synced:
                    await tc.set_permissions(role, send_messages=False)

            for vc in ctx.guild.voice_channels:
                if not vc.permissions_synced:
                    await vc.set_permissions(role, connect=False)
            for member in ctx.guild.members:
                if member.id == await self.bot.db.fetchval("SELECT userid FROM mutes WHERE guildid = $1", ctx.guild.id):
                    await member.add_roles(role, reason="Carrying over mutes")
        except discord.Forbidden:
            return "Unable to set channel permissions, please check my permissions!"

        await self.set_unset_role(ctx, role, 'mutedrole', 'set')

    @commands.guild_only()
    @commands.group(invoke_without_command=True)
    async def prefix(self, ctx):
        """Manage and list the guild's custom prefixes, by default the only avalable prefixes will be mentioning the bot or the global default prefix"""
        await ctx.send_help(ctx.command)

    @commands.guild_only()
    @checks.is_staff_or_perms("Admin", manage_guild=True)
    @prefix.command()
    async def add(self, ctx, new_prefix):
        """Adds a prefix to the bot for your guild (Admin+, or manage server) (No more than 10 per guild)"""
        new_prefix = discord.utils.escape_mentions(new_prefix)  # ha ha no
        async with self.bot.db.acquire() as conn:
            guild_prefixes = await conn.fetchval("SELECT prefixes FROM guild_settings WHERE guildid = $1", ctx.guild.id)
            if guild_prefixes is None:
                guild_prefixes = []

            if new_prefix not in guild_prefixes and len(guild_prefixes) < 10:
                await conn.execute("UPDATE guild_settings SET prefixes = array_append(prefixes, $1) WHERE guildid = $2",
                                   new_prefix, ctx.guild.id)
                return await ctx.send(f"Added prefix `{new_prefix}` as a guild prefix")
            else:
                if len(guild_prefixes) >= 10:
                    return await ctx.send("No more than 10 custom prefixes may be added!")
                else:
                    return await ctx.send("This prefix is already in the guild!")

    @commands.guild_only()
    @checks.is_staff_or_perms("Admin", manage_guild=True)
    @prefix.command(aliases=['del', 'delete'])
    async def remove(self, ctx, prefix):
        """Removes a prefix from the guild (Admin+, or Manage Server)"""
        async with self.bot.db.acquire() as conn:
            guild_prefixes = await conn.fetchval("SELECT prefixes FROM guild_settings WHERE guildid = $1", ctx.guild.id)
            if not guild_prefixes:
                return await ctx.send("No custom guild prefixes saved!")
            elif prefix not in guild_prefixes:
                return await ctx.send("This prefix is not saved to this guild!")
            else:
                await conn.execute("UPDATE guild_settings SET prefixes = array_remove(prefixes, $1) WHERE guildid = $2", prefix, ctx.guild.id)
                await ctx.send("Prefix removed!")

    @commands.guild_only()
    @prefix.command()
    async def list(self, ctx):
        """List the guild's custom prefixes"""
        guild_prefixes = await self.bot.db.fetchval("SELECT prefixes FROM guild_settings WHERE guildid = $1", ctx.guild.id)
        embed = discord.Embed(title=f"Prefixes for {ctx.guild.name}", color=common.gen_color(ctx.guild.id))
        if guild_prefixes:
            prefix_str = ""
            for prefix in guild_prefixes:
                prefix_str += f"- `{prefix}`\n"
            embed.set_footer(text=f"{len(guild_prefixes)} custom guild prefixes saved" if len(
                guild_prefixes) != 1 else "1 custom guild prefix saved")

        else:
            prefix_str = "No prefixes saved"

        embed.description = prefix_str
        embed.add_field(name="Global default prefixes", value=f"- {ctx.me.mention}\n- `{read_config('default_prefix')}`", inline=False)
        await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(Setup(bot))
