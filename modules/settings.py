import discord
from discord.ext import commands, flags
from terrygon import read_config
from utils import checks, errors, common, paginator
import typing


class Settings(commands.Cog):
    """Settings and configuration Cog"""

    def __init__(self, bot):
        self.bot = bot

    async def get_db_asset(self, asset: str, guild: discord.Guild):
        async with self.bot.db.acquire() as conn:
            if asset in ('mod_role', 'admin_role', 'owner_role', 'approved_role', 'muted_role'):
                return (await conn.fetchrow(f"SELECT {asset} FROM roles WHERE guild_id = $1", guild.id))[0]

            elif asset in ('mod_logs', 'message_logs', 'member_logs', 'filter_logs'):
                return (await conn.fetchrow(f"SELECT {asset} FROM channels WHERE guild_id = $1", guild.id))[0]

            else:
                self.bot.error_log.error("Invalid input given for asset")
                return None

    async def set_unset_role(self, ctx: commands.Context, role: typing.Union[discord.Role, None], role_type: str,
                             mode: str) -> int:
        if not isinstance(role, discord.Role) and role is not None:
            await ctx.send("Invalid role given! Does this role exist?")
            return -1

        if role_type not in ('mod_role', 'admin_role', 'owner_role', 'approved_role', 'muted_role', 'probation_role'):
            raise commands.BadArgument("Invalid Database Role")

        async with self.bot.db.acquire() as conn:

            if mode == 'unset':
                role_id = await self.get_db_asset(role_type, ctx.guild)
                if role_id is None:
                    return -1
                try:
                    role = ctx.guild.get_role(role_id)
                    if not role:
                        raise errors.LoggingError("Deleted role", ctx.guild)
                    await self.bot.terrygon_logger.log_setup("unset", f"{role_type} role", ctx.author,
                                                             role, 'mod_logs')
                except errors.LoggingError:
                    self.bot.console_output_log.warning(
                        f"Failed to log {role_type} database unset on server {ctx.guild.name}. (ID: {ctx.guild.id})")
                await conn.execute(f"UPDATE roles SET {role_type} = NULL WHERE guild_id = $1", ctx.guild.id)
                return 0

            else:
                # just in case!
                if role is None:
                    return -1

                await conn.execute(f"UPDATE roles SET {role_type} = $1 WHERE guild_id = $2", role.id, ctx.guild.id)
                try:
                    await self.bot.terrygon_logger.log_setup("set", f"{role_type} role", ctx.author,
                                                             await self.get_db_asset(role_type,
                                                                                     ctx.guild) if role is None else ctx.guild.get_role(
                                                                 role.id), 'mod_logs')
                except errors.LoggingError:
                    self.bot.console_output_log.warning(
                        f"Failed to log {role_type} database set! on server {ctx.guild.name}. (ID: {ctx.guild.id})")

                return 0

    async def set_unset_channels(self, ctx: commands.Context, channel: typing.Union[discord.TextChannel, None],
                                 channel_type: str, mode: str) -> int:
        """Sets a log channel to the database, mode should be either `set` or `unset`"""
        if not isinstance(channel, discord.TextChannel) and channel is not None:
            await ctx.send("Invalid channel, does this channel exist?")
            return -1

        if channel_type not in ('mod_logs', 'message_logs', 'member_logs', 'filter_logs'):
            raise commands.BadArgument("Invalid Database Channel")

        async with self.bot.db.acquire() as conn:
            if mode.lower() == 'unset':
                try:
                    channel_id = await self.get_db_asset(channel_type, ctx.guild)
                    if channel_id is None:
                        return -1

                    await self.bot.terrygon_logger.log_setup("unset", f"{channel_type} channel", ctx.author,
                                                             self.bot.get_channel(channel_id), channel_type)

                except errors.LoggingError:
                    self.bot.console_output_log.warning(
                        f"Failed log setting the {channel} log channel on server: {ctx.guild.name} (ID: {ctx.guild.id})")

                await conn.execute(f"UPDATE channels SET {channel_type} = NULL WHERE guild_id = $1", ctx.guild.id)
                return 0

            elif mode.lower() == 'set':
                # just in case
                if channel is None:
                    await ctx.send("Please enter a channel to set")
                    return -1

                await conn.execute(f"UPDATE channels SET {channel_type} = $1 WHERE guild_id = $2", channel.id,
                                   ctx.guild.id)

                try:
                    await self.bot.terrygon_logger.log_setup("set", f"{channel_type} channel", ctx.author, channel,
                                                             channel_type)
                except errors.LoggingError:
                    self.bot.console_output_log.warning(
                        f"Failed log setting the {channel} log channel on server: {ctx.guild.name} (ID: {ctx.guild.id})")

                return 0

            else:
                raise commands.BadArgument("Unknown mode, valid modes are set and unset!")

    # channels
    @commands.guild_only()
    @checks.is_staff_or_perms("Owner", administrator=True)
    @commands.group(name="logchannel", invoke_without_command=True)
    async def log_channel(self, ctx: commands.Context):
        """Command for setting and unsetting log channels (Owner or administrator)"""
        await ctx.send_help(ctx.command)

    # TODO: remove flag commands
    @commands.guild_only()
    @checks.is_staff_or_perms("Owner", administrator=True)
    @flags.add_flag("--modlogs", type=discord.TextChannel)
    @flags.add_flag("--memberlogs", type=discord.TextChannel)
    @flags.add_flag("--messagelogs", type=discord.TextChannel)
    @flags.add_flag("--filterlogs", type=discord.TextChannel)
    @log_channel.command(name="channelset", cls=flags.FlagCommand, aliases=['set'])
    async def channel_set(self, ctx: commands.Context, **log_channels):
        """Sets a channel to be used as a log channel (Owner or administrator)
        **Flags:**
        One or more of:
        - `--modlogs` arguments: `<channel>` logs moderation commands like warn/ban/mute/kick/lockdown
        - `--memberlogs` arguments: `<channel>` logs all data relating to users being updated, like nickname changes or role changes
        - `--messagelogs` arguments: `<channel>` logs all data relating to messages, such as edits, deletions, or pinned messages by trusted members
        - `--filterlogs` arguments: `<channel>` logs all banned words that are said
        """
        active_flags = {lst for lst in log_channels.items() if lst[1]}
        if not active_flags:
            return await ctx.send(
                "Please specify a log channel type you would like to add, flags are `--modlogs`, `--memberlogs`, `--messagelogs`, or `--filterlogs`")

        else:
            msg = ""
            async with ctx.channel.typing():
                for channel_type, channel in active_flags:
                    lst = list(channel_type)
                    lst.insert(len(channel_type) - 4, "_")
                    channel_type = ''.join(lst)
                    if await self.set_unset_channels(ctx, channel, channel_type, 'set') == 0:
                        msg += f"{channel_type.replace('_', '').title()}, "

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
    @flags.add_flag("--filterlogs", default=None, action="store_true")
    @log_channel.command(name="channelunset", cls=flags.FlagCommand, aliases=['unset'])
    async def channel_unset(self, ctx: commands.Context, **channel_type):
        """
        Unsets a log channel (Owner or administrator)

        **Flags:**
        One or more of:
        - `--modlogs` Unsets the mod logs channel.
        - `--memberlogs` Unsets the member logs channel.
        - `--messagelogs` Unsets the message logs channel.
        - `--filterlogs` Unsets the filter logs channel.
        """

        active_flags = [lst[0] for lst in channel_type.items() if lst[1]]
        if not active_flags:
            await ctx.send(
                "Please specify a log channel type you would like to remove, flags are `--modlogs`, `--memberlogs`, `--messagelogs`, and `--filterlogs`")
        else:
            msg = ""
            async with ctx.channel.typing():
                for log_type in active_flags:
                    lst = list(log_type)
                    lst.insert(len(log_type) - 4, "_")
                    log_type = ''.join(lst)
                    if await self.set_unset_channels(ctx, None, log_type, 'unset') == 0:
                        msg += f"{log_type.replace('_', '').title()}, "

            if msg:
                await ctx.send(msg.rstrip(", ") + " have been unset!")
            else:
                # should never appear
                await ctx.send("Unable to unset any channels to the database!")

    # roles
    @commands.guild_only()
    @checks.is_staff_or_perms("Owner", administrator=True)
    @commands.group(invoke_without_command=True, aliases=['serverrole', 'dbrole'], name="staffrole")
    async def staff_role(self, ctx: commands.Context):
        """Command for setting and unsetting staff roles (Owner or administrator)"""
        await ctx.send_help(ctx.command)

    @checks.is_staff_or_perms("Owner", administrator=True)
    @flags.add_flag("--adminrole", type=discord.Role)
    @flags.add_flag("--modrole", type=discord.Role)
    @flags.add_flag("--ownerrole", type=discord.Role)
    @staff_role.command(cls=flags.FlagCommand, name="set")
    async def staff_role_set(self, ctx: commands.Context, **role_flags):
        """Sets a staff role to be used in the database (Owner or administrator)

        **Flags:**
        One or more
        - `--adminrole` arguments: `<role>` Role for administrators.
        - `--ownerrole` arguments: `<role>` Role for owners.
        - `--modrole` arguments: `<role>` Role for moderators
        """
        active_flags = {lst for lst in role_flags.items() if lst[1]}
        if not active_flags:
            return await ctx.send(
                "Please specify a database role you would like to add, flags are `--adminrole`, `--modrole`, and `--ownerrole`")
        else:
            msg = ""
            async with ctx.channel.typing():
                for role_type, role in active_flags:
                    lst = list(role_type)
                    lst.insert(len(role_type) - 4, "_")
                    role_type = ''.join(lst)
                    if await self.set_unset_role(ctx, role, role_type, 'set') == 0:
                        msg += f"{role_type.replace('_', '').title()}, "

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
    async def role_unset(self, ctx: commands.Context, **role_flags):
        """Unsets a staff role (Owner or administrator)

        **Flags:**
        One or more
        - `--adminrole` Unsets the admin role
        - `--ownerrole` Unsets the owner role
        - `--modrole` Unsets the mod role
        """
        active_flags = {lst for lst in role_flags.items() if lst[1]}
        if not active_flags:
            return await ctx.send(
                "Please specify a database role you would like to add, flags are `--adminrole`, `--modrole`, and `--ownerrole`")
        else:
            msg = ""
            async with ctx.channel.typing():
                for role_type, role in active_flags:
                    lst = list(role_type)
                    lst.insert(len(role_type) - 4, "_")
                    role_type = ''.join(lst)
                    if await self.set_unset_role(ctx, None, role_type, 'unset') == 0:
                        msg += f"{role_type.replace('_', '').title()}, "

            if msg:
                await ctx.send(msg.rstrip(", ") + " have been unset!")
            else:
                # should never appear
                await ctx.send("Unable to unset any roles to the database!")

    async def toggle_join_logs(self, ctx: commands.Context):
        async with self.bot.db.acquire() as conn:
            member_logs_channel_id = await conn.fetchval("SELECT member_logs FROM channels WHERE guild_id =  $1",
                                                         ctx.guild.id)
            if member_logs_channel_id is None:
                await ctx.send("Member log channel not configured!")
                return

            if await conn.fetchval("SELECT enable_join_leave_logs FROM guild_settings WHERE guild_id = $1",
                                   ctx.guild.id):
                await conn.execute("UPDATE guild_settings SET enable_join_leave_logs = FALSE WHERE guild_id = $1",
                                   ctx.guild.id)
                await ctx.send("Join and leave logs are now off!")
                await self.bot.terrygon_logger.toggle_log_setup("unset", "join leave logs", ctx.author, 'member_logs')
            else:
                await conn.execute("UPDATE guild_settings SET enable_join_leave_logs = TRUE WHERE guild_id = $1",
                                   ctx.guild.id)
                await ctx.send("Join and leave logs are now on!")
                await self.bot.terrygon_logger.toggle_log_setup("set", "join leave logs", ctx.author, 'member_logs')

    async def toggle_core_message_logs(self, ctx: commands.Context):
        async with self.bot.db.acquire() as conn:
            member_logs_channel_id = await conn.fetchval("SELECT message_logs FROM channels WHERE guild_id =  $1",
                                                         ctx.guild.id)
            if member_logs_channel_id is None:
                await ctx.send("Message log channel not configured!")
                return

            if await conn.fetchval("SELECT enable_core_message_logs FROM guild_settings WHERE guild_id = $1",
                                   ctx.guild.id):
                await conn.execute("UPDATE guild_settings SET enable_core_message_logs = FALSE WHERE guild_id = $1",
                                   ctx.guild.id)
                await ctx.send("Message edits and deletes are no longer logged!")
                await self.bot.terrygon_logger.toggle_log_setup("unset", "core message logs", ctx.author,
                                                                'message_logs')
            else:
                await conn.execute("UPDATE guild_settings SET enable_core_message_logs = TRUE WHERE guild_id = $1",
                                   ctx.guild.id)
                await ctx.send("Message edits and deletes are now being logged!")
                await self.bot.terrygon_logger.toggle_log_setup("set", "core message logs", ctx.author, 'message_logs')

    @commands.guild_only()
    @checks.is_staff_or_perms('Owner', administrator=True)
    @commands.group(invoke_without_command=True)
    async def logs(self, ctx: commands.Context):
        """Command used to manage all logging systems. You can set and unset channels, modroles, and toggle which things you would like to log for your server"""
        await ctx.send_help(ctx.command)

    @commands.guild_only()
    @checks.is_staff_or_perms('Owner', administrator=True)
    @logs.command(name='joinleave')
    async def join_leave(self, ctx: commands.Context):
        """Enables or disables joining and leaving logs"""
        await self.toggle_join_logs(ctx)

    @commands.guild_only()
    @checks.is_staff_or_perms('Owner', administrator=True)
    @logs.command(name="editsdeletes", aliases=['coremessagelogs'])
    async def edits_and_deletes(self, ctx: commands.Context):
        """Enables or disables message edits or deletions"""
        await self.toggle_core_message_logs(ctx)

    @commands.guild_only()
    @checks.is_staff_or_perms('Mod', manage_roles=True)
    @commands.group(invoke_without_command=True, name="mutedrole")
    async def muted_role(self, ctx: commands.Context):
        """Manage muted role"""
        await ctx.send_help(ctx.command)

    @commands.guild_only()
    @checks.is_staff_or_perms('Mod', manage_roles=True)
    @muted_role.command(name="set")
    async def muted_role_set(self, ctx: commands.Context, role: discord.Role = None):
        """Sets and configures a server's muted role"""
        out = await self.muted_role_setup(ctx, role)
        if out:
            await ctx.send(out)

    @commands.guild_only()
    @checks.is_staff_or_perms('Admin', manage_guild=True)
    @muted_role.command(name="unset")
    async def muted_role_unset(self, ctx: commands.Context):
        """Unsets the muted role (Admin+, manage server)"""
        muted_role_id = await self.bot.db.fetchval("SELECT muted_role FROM roles WHERE guild_id = $1", ctx.guild.id)
        if not muted_role_id:
            return await ctx.send("No muted_role saved in the database.")
        await self.set_unset_role(ctx, None, 'muted_role', 'unset')
        res, msg = await paginator.YesNoMenu("Muted role, unset, would you like to delete it?").prompt(ctx)
        if res:
            try:
                await ctx.guild.get_role(muted_role_id).delete()
                await msg.edit(content="Role deleted!")
            except discord.Forbidden:
                return await msg.edit(content="I cannot delete roles!")
        else:
            await msg.edit(content="Role not deleted.")

    async def muted_role_setup(self, ctx: commands.Context, role: discord.Role = None):
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

        # first go through the categories
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
                if member.id == await self.bot.db.fetchval("SELECT user_id FROM mutes WHERE guild_id = $1",
                                                           ctx.guild.id):
                    await member.add_roles(role, reason="Carrying over mutes")
        except discord.Forbidden:
            return "Unable to set channel permissions, please check my permissions!"

        await self.set_unset_role(ctx, role, 'muted_role', 'set')

    @commands.guild_only()
    @checks.is_staff_or_perms("Admin", manage_roles=True, manage_channels=True)
    @commands.group(name="probation", aliases=['probationsetup'], invoke_without_command=True)
    async def probation_settings(self, ctx: commands.Context):
        """Probation setup commands"""
        await ctx.send_help(ctx.command)

    @commands.guild_only()
    @checks.is_staff_or_perms("Admin", manage_roles=True, manage_channels=True)
    @flags.add_flag("--channel", '-c', type=discord.TextChannel, default=None)
    @flags.add_flag("--role", '-r', type=discord.Role, default=None)
    @probation_settings.command(name="configure", aliases=['set', 'setup'], cls=flags.FlagCommand)
    async def probate_configure(self, ctx: commands.Context, **kwargs):
        """Probation configuration"""
        res = await self.probate_setup(ctx, **kwargs)
        if res == -1:
            return await ctx.send("Unable to configure probation, please try again.")

    async def probate_setup(self, ctx: commands.Context, **kwargs) -> int:
        """Sets up probation"""
        probation_role = None
        probation_channel = None
        if not kwargs['channel']:
            res, msg = await paginator.YesNoMenu(
                "No probation channel set, would you like to create a new one and set it?").prompt(ctx)
            if res:
                try:
                    probation_channel = await ctx.guild.create_text_channel('probation',
                                                                            reason="Probation lockdown channel")
                except discord.Forbidden:
                    return await msg.edit(content="Unable to manage channels")

                await msg.edit(content="Probation channel created!")

            else:
                await msg.edit(
                    content="You need a probation channel to lock users to. If you have an existing one please set it with `-c <channel>`")
                return -1
        else:
            probation_channel = kwargs['channel']

        if not kwargs['role']:
            res, msg = await paginator.YesNoMenu("No probation role set, would you like to make one?").prompt(ctx)
            if res:
                try:
                    probation_role = await ctx.guild.create_role(name="Probation", color=discord.Color.dark_red())
                except discord.Forbidden:
                    return await msg.edit(content="I cannot manage roles!")

                await msg.edit(content="Probation role created!")

            else:
                await msg.edit(
                    content="You need a probation role for probate to work properly. If you have an existing one please specify one with `-r <role>`")
                return -1

        else:
            probation_role = kwargs['role']

        # enter data into database
        if probation_role is None or probation_channel is None:
            await ctx.send("Invalid data given, please run this command again.")
            return -1

        await self.bot.db.execute("UPDATE channels SET probation_channel = $1 WHERE guild_id = $2",
                                  probation_channel.id, ctx.guild.id)
        await self.bot.db.execute("UPDATE roles SET probation_role = $1 WHERE guild_id = $2", probation_role.id,
                                  ctx.guild.id)

        # set permissions
        async with ctx.channel.typing():
            try:
                # roles
                for channel in ctx.guild.channels:
                    if channel == probation_channel or channel.permissions_synced:
                        continue

                    elif (channel.type == discord.ChannelType.category) or (
                            channel.type == discord.ChannelType.text and not channel.permissions_synced):
                        await channel.set_permissions(probation_role, read_messages=False)

            except discord.Forbidden:
                await ctx.send("Unable to manage roles.")
                return -1

            # channel
            await probation_channel.set_permissions(probation_role, read_messages=True, send_messages=None,
                                                    read_message_history=True, add_reactions=False, attach_files=False, embed_links=False)
            staff_roles_id = await self.bot.db.fetchrow(
                "SELECT mod_role, admin_role, owner_role FROM roles WHERE guild_id = $1", ctx.guild.id)

            await probation_channel.set_permissions(ctx.guild.default_role, read_messages=False)
            if staff_roles_id:
                staff_roles = []
                for r_id in staff_roles_id:
                    role = ctx.guild.get_role(r_id)
                    if role:
                        staff_roles.append(role)

                if staff_roles:
                    for role in staff_roles:
                        await probation_channel.set_permissions(role, read_messages=True)

        await ctx.send("Probation channel and role set up.")
        await self.bot.terrygon_logger.probation_settings("set", ctx.author, probation_channel, probation_role)
        return 0

    @commands.guild_only()
    @checks.is_staff_or_perms("Mod", manage_roles=True, manage_channels=True)
    @probation_settings.command(name="unset", aliases=['unconfigure'])
    async def probation_unset(self, ctx: commands.Context):
        """Removes a probation system."""
        probation_role_id = await self.bot.db.fetchval("SELECT probation_role FROM roles WHERE guild_id = $1",
                                                       ctx.guild.id)
        probation_channel_id = await self.bot.db.fetchval("SELECT probation_channel FROM channels WHERE guild_id = $1",
                                                          ctx.guild.id)
        probation_role = ctx.guild.get_role(probation_role_id)
        probation_channel = ctx.guild.get_channel(probation_channel_id)

        await self.bot.db.execute("UPDATE roles SET probation_role = NULL WHERE guild_id = $1", ctx.guild.id)
        if probation_role:
            res, msg = await paginator.YesNoMenu(
                "Would you like to delete the probation role? This will unprobate all users.").prompt(ctx)
            if res:
                try:
                    await probation_role.delete(reason="Removing probation system.")
                    await msg.edit(content="Probation role deleted.")
                except discord.Forbidden:
                    await msg.edit(content="Unable to delete roles due to permissions.")

            else:
                await msg.edit(content="Role not deleted.")

        else:
            await ctx.send("Probation role has already been deleted, removing from database.")

        await self.bot.db.execute("UPDATE channels SET probation_channel = NULL WHERE guild_id = $1", ctx.guild.id)
        if probation_channel:
            res, msg = await paginator.YesNoMenu("Would you like to delete the probation channel?").prompt(ctx)
            if res:
                try:
                    await probation_channel.delete(reason="Removing probation system.")
                    await msg.edit(content="Probation channel deleted")
                except discord.Forbidden:
                    await msg.edit(content="I cannot delete channels")
            else:
                await msg.edit(content="Channel not deleted.")
        else:
            await ctx.send("Probation channel has already been deleted")

        await self.bot.db.execute("DELETE FROM probations WHERE guild_id = $1", ctx.guild.id)
        await self.bot.db.execute("UPDATE guild_settings SET auto_probate = FALSE WHERE guild_id = $1", ctx.guild.id)
        await ctx.send("Probation system removed.")
        await self.bot.terrygon_logger.probation_settings("unset", ctx.author)

    @commands.guild_only()
    @checks.is_staff_or_perms("Mod", manage_roles=True, manage_channels=True)
    @probation_settings.command(name="list")
    async def probation_list(self, ctx: commands.Context):
        """Shows probation settings"""
        c_id = await self.bot.db.fetchval("SELECT probation_channel FROM channels WHERE guild_id = $1", ctx.guild.id)
        r_id = await self.bot.db.fetchval("SELECT probation_role FROM roles WHERE guild_id = $1", ctx.guild.id)
        probation_channel = ctx.guild.get_channel(c_id)
        probation_role = ctx.guild.get_role(r_id)
        emb = discord.Embed(title=f"Probation settings for {ctx.guild.name}")
        if probation_channel:
            desc = f"Probation channel: {probation_channel.mention}\n"
        elif not probation_channel and c_id:
            desc = f"Probation channel has been deleted, please reconfigure probation: ID: {c_id}\n"
        else:
            desc = "No probation channel set.\n"

        if probation_role:
            desc += f"Probation role: **{probation_role.name}**\n"
        elif not probation_role and r_id:
            desc += f"Probation role has been deleted, please reconfigure probation: Role ID {r_id}\n"
        else:
            desc += f"No probation role set.\n"

        status = await self.bot.db.fetchval("SELECT auto_probate FROM guild_settings WHERE guild_id = $1", ctx.guild.id)

        if status:
            desc += "Auto probate is currently enabled. To disable, please run `autoprobate disable`"
        else:
            desc += "Auto probate is currently disabled. To enable, please run `autoprobate enable`"

        emb.description = desc
        await ctx.send(embed=emb)

    @commands.guild_only()
    @commands.group(invoke_without_command=True)
    async def prefix(self, ctx: commands.Context):
        """Manage and list the guild's custom prefixes, by default the only available prefixes will be mentioning the bot or the global default prefix"""
        await ctx.send_help(ctx.command)

    @commands.guild_only()
    @checks.is_staff_or_perms("Admin", manage_guild=True)
    @prefix.command()
    async def add(self, ctx: commands.Context, new_prefix: str):
        """Adds a prefix to the bot for your guild (Admin+, or manage server) (No more than 10 per guild)"""
        new_prefix = discord.utils.escape_mentions(new_prefix)  # ha ha no
        async with self.bot.db.acquire() as conn:
            guild_prefixes = await conn.fetchval("SELECT prefixes FROM guild_settings WHERE guild_id = $1",
                                                 ctx.guild.id)
            if guild_prefixes is None:
                guild_prefixes = []

            if new_prefix not in guild_prefixes and len(guild_prefixes) < 10:
                await conn.execute(
                    "UPDATE guild_settings SET prefixes = array_append(prefixes, $1) WHERE guild_id = $2",
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
    async def remove(self, ctx: commands.Context, prefix: str):
        """Removes a prefix from the guild (Admin+, or Manage Server)"""
        async with self.bot.db.acquire() as conn:
            guild_prefixes = await conn.fetchval("SELECT prefixes FROM guild_settings WHERE guild_id = $1",
                                                 ctx.guild.id)
            if not guild_prefixes:
                return await ctx.send("No custom guild prefixes saved!")
            elif prefix not in guild_prefixes:
                return await ctx.send("This prefix is not saved to this guild!")
            else:
                await conn.execute(
                    "UPDATE guild_settings SET prefixes = array_remove(prefixes, $1) WHERE guild_id = $2",
                    prefix, ctx.guild.id)
                await ctx.send("Prefix removed!")

    @commands.guild_only()
    @prefix.command()
    async def list(self, ctx: commands.Context):
        """List the guild's custom prefixes"""
        guild_prefixes = await self.bot.db.fetchval("SELECT prefixes FROM guild_settings WHERE guild_id = $1",
                                                    ctx.guild.id)
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
        embed.add_field(name="Global default prefixes",
                        value=f"- {ctx.me.mention}\n- `{read_config('info', 'default_prefix')}`", inline=False)
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Settings(bot))
