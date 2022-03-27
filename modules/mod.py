import discord
from discord.ext import commands, flags
import typing
from utils import checks, common, errors
from datetime import datetime, timedelta


# TODO: Seperate out simailar code into single functions, break up massive commands such as mute or probate.
# TODO: Merge functionality of probate and approval configure.

class Mod(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    # mute commands
    async def silent_mute_prep(self, member: discord.Member, mode: str) -> int:
        """Sets up mutes without output, this should only be called after permissions have been checked"""
        async with self.bot.db.acquire() as conn:
            muted_role_id = await conn.fetchval("SELECT muted_role FROM roles WHERE guild_id = $1", member.guild.id)
            if not muted_role_id:
                return -1  # no wizard to set up muted role, please use regular version for that

            muted_role = member.guild.get_role(muted_role_id)
            if not muted_role:
                return -1
            try:
                query_output = await conn.fetchval(
                    "SELECT user_id FROM mutes WHERE user_id = $1 AND guild_id = $2", member.id,
                    member.guild.id)
                if muted_role in member.roles or query_output == member.id:
                    if mode == 'timed':
                        return 1
                    else:
                        return -1
            except TypeError:
                pass

        try:
            await member.add_roles(muted_role)
        except discord.Forbidden:
            return -1

        return 0

    async def mute_prep(self, ctx: commands.Context, member: discord.Member, mode: str) -> int:
        """Sets up the mute commands"""
        mod_bot_protection = await checks.mod_bot_protection(self.bot, ctx, member, "mute")
        if mod_bot_protection is not None:
            await ctx.send(mod_bot_protection)
            return -1

        async with self.bot.db.acquire() as conn:
            muted_role_id = await conn.fetchval("SELECT muted_role FROM roles WHERE guild_id = $1", ctx.guild.id)
            muted_role = ctx.guild.get_role(muted_role_id)
            if muted_role_id is None or muted_role is None:
                cog = self.bot.get_cog('Settings')
                if not cog:
                    msg = "Set up cog not loaded and muted role not set, please manually set the muted role or load the setup cog to trigger the wizard"
                    self.bot.error_log.error(
                        f"Command: {ctx.command} Guild: {ctx.guild} (ID: {ctx.guild.id})\n " + msg + "\n")
                    await ctx.send(msg)
                    return -1
                await cog.muted_role_setup(ctx)
                muted_role_id = await conn.fetchval("SELECT muted_role FROM roles WHERE guild_id = $1", ctx.guild.id)
                muted_role = ctx.guild.get_role(muted_role_id)
                if not muted_role and not muted_role_id:
                    await ctx.send(
                        "Cannot proceed with mute due to muted role not being configured. Please run the mutedrole command to configure.")
                    return -1

            try:
                if muted_role in member.roles or await conn.fetchval(
                        "SELECT user_id FROM mutes WHERE user_id = $1 AND guild_id = $2", member.id,
                        ctx.guild.id) == member.id:
                    if mode == 'timed':
                        await ctx.send("User is already muted, converting to timed mute")
                        return 1
                    else:
                        await ctx.send("User is already muted")
                    return -1
            except TypeError:
                pass

            try:
                await member.add_roles(muted_role)
            except discord.Forbidden:
                await ctx.send("💢 I don't have permission to do this.")
                return -1

            return 0

    @commands.guild_only()
    @checks.is_staff_or_perms("Mod", manage_roles=True)
    @commands.command()
    async def mute(self, ctx: commands.Context, member: discord.Member, *, reason: str = None):
        res = await self.mute_prep(ctx, member, 'normal')
        """Mutes a member so they cannot speak in the server. (Mod+, manage_roles)"""
        if res == -1:
            return

        await self.bot.db.execute("INSERT INTO mutes (user_id, author_id, guild_id, reason) VALUES ($1, $2, $3, $4)",
                                  member.id, ctx.author.id, ctx.guild.id, reason)

        msg = f"You have been muted in {ctx.guild.name}"
        if reason is not None:
            msg += f" for the following reason: {reason}"

        try:
            await member.send(msg)
        except discord.Forbidden:
            pass
        await self.bot.terrygon_logger.mod_logs(ctx, 'mute', member, ctx.author, reason)

        await ctx.send(f"{member} has been muted.")

    @commands.guild_only()
    @checks.is_staff_or_perms("Mod", manage_roles=True)
    @commands.command(name='timemute')
    async def time_mute(self, ctx: commands.Context, member: discord.Member, time: str, *, reason: str = None):
        """Mutes a member for a limited number of time (Use dhms format, for example `5m` would be 5 minutes) (Mod+)"""
        time_seconds = common.parse_time(time)
        if time_seconds == -1:
            return await ctx.send("Invalid time passed, please make sure its in the dhms format.")

        res = await self.mute_prep(ctx, member, 'timed')
        if res == -1:
            return
        elif res == 1:
            m_id = await self.bot.db.fetchval("SELECT id FROM mutes WHERE user_id = $1 AND guild_id = $2", member.id,
                                              ctx.guild.id)
        else:
            m_id = await self.bot.db.fetchval(
                "INSERT INTO mutes (user_id, author_id, guild_id, reason) VALUES ($1, $2, $3, $4) RETURNING id",
                member.id, ctx.author.id, ctx.guild.id, reason)

        ts = (datetime.utcnow() + timedelta(seconds=time_seconds))
        await ctx.send(f"{member} has been muted until {ts.strftime('%Y-%m-%d %H:%M:%S')} UTC")
        try:
            msg = f"You have been muted on {ctx.guild.name} until {ts.strftime('%Y-%m -%d %H:%M:%S')}"
            if reason:
                msg += f" for the reason: `{reason}`"
            await member.send(msg)
        except discord.Forbidden:
            pass
        try:
            await self.bot.terrygon_logger.timed_mod_logs('mute', member, ctx.author, ts, reason)
        except errors.LoggingError:
            pass

        await self.bot.scheduler.add_timed_job('mute', datetime.utcnow(), timedelta(seconds=time_seconds),
                                               action_id=m_id)

    @commands.guild_only()
    @checks.is_staff_or_perms("Mod", manage_roles=True)
    @commands.command()
    async def unmute(self, ctx: commands.Context, member: discord.Member):
        """Unmutes a member so they can speak again. (Mod+, manage_roles)"""
        # protect against staff muting each other or self
        mod_bot_protection = await checks.mod_bot_protection(self.bot, ctx, member, "unmute")
        if mod_bot_protection is not None:
            await ctx.send(mod_bot_protection)
            return

        # get muted role and make sure it exists
        async with self.bot.db.acquire() as conn:
            muted_role_id = await conn.fetchval("SELECT muted_role FROM roles WHERE guild_id = $1", ctx.guild.id)
            muted_role = ctx.guild.get_role(muted_role_id)

            if muted_role_id is None or muted_role is None:
                await ctx.send(
                    "Muted role not configured. Please run <muted set up command>")  # TODO: fix unmute not configured message

            try:
                query_output = await conn.fetchval("SELECT user_id FROM mutes WHERE user_id = $1 AND guild_id = $2",
                                                   member.id, ctx.guild.id)
                if not muted_role in member.roles and not query_output == member.id:
                    await ctx.send("User is not muted")
                    return
            except TypeError:
                pass

            # unmute and remove entry from db
            try:
                await member.remove_roles(muted_role)
            except discord.Forbidden:
                await ctx.send("💢 I dont have permission to do this.")
                return

            await conn.execute("DELETE FROM mutes WHERE user_id = $1 AND guild_id = $2", member.id, ctx.guild.id)

            await ctx.send(f"{member} has been unmuted.")
            # logging
            await self.bot.terrygon_logger.mod_logs(ctx, 'unmute', member, ctx.author)

    async def silent_probation(self, member: discord.Member, author_id: int, reason: str) -> int:
        """Silently prepares and probates a user."""
        probation_role_id = await self.bot.db.fetchval("SELECT probation_role FROM roles WHERE guild_id = $1",
                                                       member.guild.id)
        probation_role = member.guild.get_role(probation_role_id)
        if probation_role_id is None or probation_role is None:
            return -1

        probate_id = await self.bot.db.fetchval("SELECT id FROM probations WHERE user_id = $1 AND guild_id = $2",
                                                member.id, member.guild.id)
        if probation_role in member.roles or probate_id:
            return -1

        user_role_ids = [role.id for role in member.roles if
                         role != probation_role and role != member.guild.default_role]
        try:
            await member.add_roles(probation_role)
            user_roles = [role for role in member.roles if role != probation_role and role != member.guild.default_role]
            await member.remove_roles(*user_roles, reason="User probated.")
        except discord.Forbidden:
            pass

        await self.bot.db.execute(
            "INSERT INTO probations (user_id, author_id, guild_id, roles, reason) VALUES ($1, $2, $3, $4, $5)",
            member.id, author_id, member.guild.id, user_role_ids, reason)

        return 0

    @commands.guild_only()
    @checks.is_staff_or_perms("Mod", manage_roles=True)
    @commands.command()
    async def probate(self, ctx: commands.Context, member: discord.Member, *, reason: str = None):
        """Locks a user to a purgatory channel. (Mod)"""
        mod_bot_protection = await checks.mod_bot_protection(self.bot, ctx, member, "probate")
        if mod_bot_protection is not None:
            await ctx.send(mod_bot_protection)
            return

        probation_role_id = await self.bot.db.fetchval("SELECT probation_role FROM roles WHERE guild_id = $1",
                                                       ctx.guild.id)
        probation_role = ctx.guild.get_role(probation_role_id)
        if probation_role_id is None or probation_role is None:
            cog = self.bot.get_cog("Settings")
            if not cog:
                msg = "Set up cog not loaded and muted role not set, please manually set the muted role or load the setup cog to trigger the wizard"
                self.bot.error_log.error(
                    f"Command: {ctx.command} Guild: {ctx.guild} (ID: {ctx.guild.id})\n" + msg + "\n")
                return await ctx.send(msg)

            res = await cog.probate_setup(ctx, channel=None, role=None)
            if res == -1:
                return await ctx.send("Unable to probate user, probation not configured properly.")
            else:
                probation_role_id = await self.bot.db.fetchval("SELECT probation_role FROM roles WHERE guild_id = $1",
                                                               ctx.guild.id)
                probation_role = ctx.guild.get_role(probation_role_id)

        if probation_role in member.roles or await self.bot.db.fetchval(
                "SELECT id FROM probations WHERE user_id = $1 AND guild_id = $2", member.id, ctx.guild.id):
            return await ctx.send("User is already probated.")

        user_role_ids = [role.id for role in member.roles if role != probation_role and role != ctx.guild.default_role]
        try:
            await member.add_roles(probation_role)
            user_roles = [role for role in member.roles if role != probation_role and role != ctx.guild.default_role]
            await member.remove_roles(*user_roles, reason="User probated.")
        except discord.Forbidden:
            pass

        await self.bot.db.execute(
            "INSERT INTO probations (user_id, author_id, guild_id, reason, roles) VALUES ($1, $2, $3, $4, $5)",
            member.id,
            ctx.author.id, ctx.guild.id, reason, user_role_ids)
        msg = "You are under probation!"
        if reason:
            msg += f"\nFor the reason: {reason}"

        try:
            await member.send(msg)
        except discord.Forbidden:
            pass

        await ctx.send(f"{member} is now in probation.")
        await self.bot.terrygon_logger.probation_log("probate", member, ctx.author, reason)

    @commands.guild_only()
    @checks.is_staff_or_perms("Mod", manage_roles=True)
    @commands.command()
    async def unprobate(self, ctx: commands.Context, member: discord.Member):
        """Removes a user from probation (Mod+)"""
        probation_role_id = await self.bot.db.fetchval("SELECT probation_role FROM roles WHERE guild_id = $1",
                                                       ctx.guild.id)
        probation_role = ctx.guild.get_role(probation_role_id)
        if probation_role_id is None and probation_role is None:
            return await ctx.send("Probation system not configured, this cannot be used.")
        elif probation_role_id and not probation_role:
            return await ctx.send("The probation role has been deleted from the server, please reconfigure.")

        user_role_ids = await self.bot.db.fetchval("SELECT roles FROM probations WHERE user_id = $1 AND guild_id = $2",
                                                   member.id, ctx.guild.id)

        probation_id = await self.bot.db.fetchval("SELECT id FROM probations WHERE user_id = $1 AND guild_id = $2",
                                                  member.id, ctx.guild.id)
        if not probation_id:
            return await ctx.send("User is not probated.")

        try:
            await member.remove_roles(probation_role)
            if user_role_ids:
                user_roles = []
                for r in user_role_ids:
                    role = ctx.guild.get_role(r)
                    if r:
                        user_roles.append(role)
                if user_roles:
                    await member.add_roles(*user_roles, reason="Restoring probation roles.")
        except discord.Forbidden:
            pass

        await self.bot.db.execute("DELETE FROM probations WHERE id = $1", probation_id)

        try:
            await member.send("You are out of probation.")
        except discord.Forbidden:
            pass

        await ctx.send(f"{member} is no longer in probation.")
        await self.bot.terrygon_logger.probation_log("unprobate", member, ctx.author)

    # lockdown commands
    @commands.guild_only()
    @checks.is_staff_or_perms("Mod", manage_channels=True)
    @flags.add_flag("--channel", "-c", type=discord.TextChannel, default=None)
    @flags.add_flag("--reason", '-r', type=str, default="", nargs="+")
    @flags.command(aliases=['lock'], )
    async def lockdown(self, ctx: commands.Context, **flag_args):
        """
        Locks a channel (Mod or manage channels)

        **FLAGS:**
        Optional:
        `-c` or `--channel` arguments: `<channel>` This flag allows you to specify what channel you want to lock. If you don't use this flag, it will lock the channel the command is ran in.
        `-r` or `--reason` arguments: `[reason]...` The reason given for why a channel has been locked, this flag must be at the end as it will register everything after it as the reason.
        """
        staff_roles = await common.get_staff_roles(ctx)
        channel = flag_args['channel']
        if channel is None:
            channel = ctx.channel
        elif channel.id != ctx.channel.id:
            await ctx.send(f"{self.bot.terrygon_logger.emotes['lock']} {channel.mention} has been locked.")

        # set staff roles and bot perms in place
        for role in staff_roles:
            if channel.overwrites_for(role).send_messages is False:
                await channel.set_permissions(role, send_messages=True)
        await channel.set_permissions(ctx.me, send_messages=True)

        # iterate through all applied perms and set them accordingly
        error_string = ""
        for overwrite, perm_overwrite_obj in channel.overwrites.items():
            if isinstance(overwrite, discord.Role):
                if overwrite not in staff_roles:
                    try:
                        perm_overwrite_obj.send_messages = False
                        perm_overwrite_obj.add_reactions = False
                        await channel.set_permissions(overwrite, overwrite=perm_overwrite_obj)
                    except discord.Forbidden:
                        if not error_string:
                            error_string = "I was unable to lock all the permissions in this channel!"
                        continue
            elif isinstance(overwrite, discord.Member):
                if channel.overwrites_for(overwrite).send_messages and channel.permissions_for(
                        overwrite).manage_channels is False and overwrite != ctx.me:
                    try:
                        perm_overwrite_obj.send_messages = False
                        perm_overwrite_obj.add_reactions = False
                        await channel.set_permissions(overwrite, overwrite=perm_overwrite_obj)
                    except discord.Forbidden:
                        if not error_string:
                            error_string = "I was unable to lock all the permissions in this channel!"
                        continue

        channel_lock_msg = f"{self.bot.terrygon_logger.emotes['lock']} Channel locked."
        reason = None
        if flag_args['reason']:
            reason = ' '.join(flag_args['reason'])
        if reason:
            channel_lock_msg += f" The reason is `{reason}`"
        if error_string:
            channel_lock_msg += f" But, {error_string}"
        await channel.send(channel_lock_msg)
        await self.bot.terrygon_logger.mod_logs(ctx, "lock", channel, ctx.author, reason)

    @commands.guild_only()
    @checks.is_staff_or_perms("Mod", manage_channels=True)
    @flags.add_flag("--channel", '-c', type=discord.TextChannel, default=None)
    @flags.command(aliases=['unlock'], )
    async def unlockdown(self, ctx: commands.Context, **flag_args):
        """Unlocks a channel, -c flag is not needed for unlocking the channel the command is invoked in"""

        staff_roles = await common.get_staff_roles(ctx)
        channel = flag_args['channel']
        if channel is None:
            channel = ctx.channel
        else:
            await ctx.send(f"{self.bot.terrygon_logger.emotes['unlock']} {channel.mention} has been unlocked.")

        # set staff roles and bot perms in place
        for role in staff_roles:
            if channel.overwrites_for(role).send_messages is False:
                await channel.set_permissions(role, send_messages=None)
        await channel.set_permissions(ctx.me, send_messages=None)

        # iterate through all applied perms and set them accordingly
        error_string = ""
        for overwrite, perm_overwrite_obj in channel.overwrites.items():
            if isinstance(overwrite, discord.Role):
                if overwrite not in staff_roles and overwrite.id != await self.bot.db.fetchval(
                        "SELECT muted_role FROM roles WHERE guild_id = $1", ctx.guild.id):
                    try:
                        perm_overwrite_obj.send_messages = None
                        perm_overwrite_obj.add_reactions = None
                        await channel.set_permissions(overwrite, overwrite=perm_overwrite_obj)
                    except discord.Forbidden:
                        if not error_string:
                            error_string = "I was unable to unlock all the permissions in this channel!"
                        continue
            elif isinstance(overwrite, discord.Member):
                if channel.overwrites_for(overwrite).send_messages and channel.permissions_for(
                        overwrite).manage_channels is False and overwrite != ctx.me:
                    try:
                        perm_overwrite_obj.send_messages = False
                        perm_overwrite_obj.add_reactions = False
                        await channel.set_permissions(overwrite, overwrite=perm_overwrite_obj)
                    except discord.Forbidden:
                        if not error_string:
                            error_string = "I was unable to unlock all the permissions in this channel!"
                        continue

        channel_lock_msg = f"{self.bot.terrygon_logger.emotes['unlock']} Channel unlocked."
        if error_string:
            channel_lock_msg += f" But, {error_string}"
        await channel.send(channel_lock_msg)
        await self.bot.terrygon_logger.mod_logs(ctx, "unlock", channel, ctx.author)

    # kick and ban commands

    async def remove_from_approval_list(self, member: discord.Member, guild: discord.Guild):
        async with self.bot.db.acquire() as conn:
            if not await conn.fetchval("SELECT approval_system FROM guild_settings WHERE guild_id = $1", guild.id):
                return
            else:
                if not await conn.fetchval("SELECT * FROM approved_members WHERE guild_id = $1 AND user_id = $2",
                                           guild.id,
                                           member.id):
                    return
                else:
                    await conn.fetchval("DELETE FROM approved_members WHERE user_id = $1 AND guild_id = $2", member.id,
                                        guild.id)

    @commands.guild_only()
    @checks.is_staff_or_perms("Mod", kick_members=True)
    @commands.command()
    async def kick(self, ctx: commands.Context, member: discord.Member, *, reason: str = None):
        """Kick a member. (Mod+)"""
        mod_bot_protection = await checks.mod_bot_protection(self.bot, ctx, member, "kick")
        if mod_bot_protection is not None:
            await ctx.send(mod_bot_protection)
            return

        msg = f"You have been kicked from {ctx.guild.name}"
        if reason:
            msg += f" for the following reason: `{reason}`"

        try:
            try:
                await member.send(msg)
            except discord.Forbidden:
                pass

            await self.remove_from_approval_list(member, ctx.guild)
            await member.kick(reason=reason if reason is not None else "No reason given")
        except discord.Forbidden:
            await ctx.send("Unable to kick discord.Member, check my permissions!")
            return

        await ctx.send(
            f"{member.name}#{member.discriminator} has been kicked {self.bot.terrygon_logger.emotes['kick']}")
        await self.bot.terrygon_logger.mod_logs(ctx, 'kick', member, ctx.author, reason)

    async def ban_prep(self, ctx, member, mode, **kwargs) -> discord.Member or discord.User:
        """Boiler plate ban code"""
        if isinstance(member, int):
            try:
                member = await self.bot.fetch_user(member)  # calls the api to find and ban the user
            except discord.NotFound:
                return await ctx.send("User was not found")
        else:
            mod_bot_protection = await checks.mod_bot_protection(self.bot, ctx, member, "ban")
            if mod_bot_protection is not None:
                await ctx.send(mod_bot_protection)
                return

        if isinstance(member, discord.Member):
            if mode == 'timed':
                msg = f"You have been banned from {ctx.guild.name} until {kwargs['timestamp'].strftime('%Y-%m -%d %H:%M:%S')}."
            else:
                msg = f"You have been banned from {ctx.guild.name}. This ban does not expire"

            if kwargs['reason']:
                msg += f" for the following reason: `{kwargs['reason']}`"

            try:
                await member.send(msg)
            except discord.Forbidden:
                pass
            await self.remove_from_approval_list(member, ctx.guild)

        return member

    @commands.guild_only()
    @checks.is_staff_or_perms("Admin", ban_members=True)
    @commands.command(aliases=['yeet'])
    async def ban(self, ctx: commands.Context, member: typing.Union[discord.Member, int],
                  message_deletion_number: typing.Optional[int] = 0, *, reason: str = None):
        """Ban a member. (Admin+)"""
        user = await self.ban_prep(ctx, member, 'normal', reason=reason)
        if not user:
            return

        try:
            await ctx.guild.ban(user, reason=reason if reason is not None else "No reason given",
                                delete_message_days=message_deletion_number)
        except discord.Forbidden:
            await ctx.send("I am unable to ban, check permissions!")
            return

        await ctx.send(f"{user.name}#{user.discriminator} has been banned {self.bot.terrygon_logger.emotes['ban']}")
        await self.bot.terrygon_logger.mod_logs(ctx, 'ban', user, ctx.author, reason)

    @commands.guild_only()
    @checks.is_staff_or_perms("Admin", ban_members=True)
    @commands.command(name="timeban")
    async def time_ban(self, ctx: commands.Context, member: typing.Union[discord.Member, int], time: str,
                       message_deletion_number: typing.Optional[int] = 0, *,
                       reason: str = None):
        """Bans a user for a limited amount of time. Time must be in dhms format: (example: 5m is 5 minutes)(Admin+ or ban perms)"""
        time_seconds = common.parse_time(time)
        if time_seconds == -1:
            return await ctx.send("Invalid time passed, please make sure its in the dhms format.")
        ts = (datetime.utcnow() + timedelta(seconds=time_seconds))
        user = await self.ban_prep(ctx, member, 'timed', timestamp=ts, reason=reason)
        if not user:
            return
        try:
            await ctx.guild.ban(user, reason=reason if reason else "No reason given",
                                delete_message_days=message_deletion_number)
        except discord.Forbidden:
            return await ctx.send("I am unable to ban, check permissions!")
        if reason:
            query = "INSERT INTO bans (user_id, author_id, guild_id, reason) VALUES ($1, $2, $3, $4) RETURNING id"
            args = [user.id, ctx.author.id, ctx.guild.id, reason]
        else:
            query = "INSERT INTO bans (user_id, author_id, guild_id) VALUES ($1, $2, $3) RETURNING id"
            args = [user.id, ctx.author.id, ctx.guild.id]

        b_id = await self.bot.db.fetchval(query, *args)
        await ctx.send(
            f"{user} has been banned until {ts.strftime('%Y-%m -%d %H:%M:%S')} {self.bot.terrygon_logger.emotes['ban']}")
        try:
            await self.bot.terrygon_logger.timed_mod_logs("ban", user, ctx.author, ts, reason)
        except errors.LoggingError:
            pass

        await self.bot.scheduler.add_timed_job("ban", datetime.utcnow(), timedelta(seconds=time_seconds),
                                               action_id=b_id)

    @commands.guild_only()
    @checks.is_staff_or_perms("Admin", ban_members=True)
    @commands.command()
    async def softban(self, ctx: commands.Context, member: typing.Union[discord.Member, int], *, reason: str = None):

        if isinstance(member, int):
            member = await self.bot.fetch_user(member)

        elif isinstance(member, discord.Member):
            mod_bot_protection = await checks.mod_bot_protection(self.bot, ctx, member, "softban")
            if mod_bot_protection is not None:
                await ctx.send(mod_bot_protection)
                return

            msg = f"You have been softbanned from {ctx.guild.name}"
            if reason:
                msg += f"\nThe reason is: `{reason}`"

            try:
                try:
                    await member.send(msg)
                except discord.Forbidden:
                    pass

                await self.remove_from_approval_list(member, ctx.guild)
                await member.kick(
                    reason="softbanned:" + f"The reason is {reason}" if reason is not None else "No given reason")
            except discord.Forbidden:
                await ctx.send("Unable to softban member")

        await self.bot.db.execute("INSERT INTO bans (user_id, author_id, guild_id, reason) VALUES ($1, $2, $3, $4)",
                                  member.id, ctx.author.id, ctx.guild.id, reason)

        await ctx.send(
            f"{member.name}#{member.discriminator} has been softbanned {self.bot.terrygon_logger.emotes['ban']}")
        await self.bot.terrygon_logger.mod_logs(ctx, 'softban', member, ctx.author, reason)

    @commands.guild_only()
    @checks.is_staff_or_perms("Admin", ban_members=True)
    @commands.command(name="unsoftban")
    async def unsoftban(self, ctx: commands.Context, user: int):
        """Unsoftbans a user"""
        member = await self.bot.fetch_user(user)
        if member is None:
            return await ctx.send("User does not exist")
        async with self.bot.db.acquire() as conn:
            if await conn.fetchval("SELECT * FROM bans WHERE user_id = $1 AND guild_id = $2", member.id, ctx.guild.id):
                await conn.execute("DELETE FROM bans WHERE user_id = $1 AND guild_id = $2",
                                   member.id, ctx.guild.id)
            else:
                return await ctx.send("User is not softbanned")

        await ctx.send(
            f"{member.name}#{member.discriminator} has been unsoftbanned {self.bot.terrygon_logger.emotes['warn']}")

        await self.bot.terrygon_logger.unsoftban_log(ctx, member)

    @commands.guild_only()
    @checks.is_staff_or_perms("Admin", ban_members=True)
    @commands.command()
    async def unban(self, ctx: commands.Context, user_id: int):
        """Unbans a user from the server (NOT FOR SOFTBANS)"""
        member = await self.bot.fetch_user(user_id)
        if not member:
            return await ctx.send("This user ID is either invalid or the user has deleted their account.")

        await ctx.guild.unban(member)
        await self.bot.terrygon_logger.unban_log(member, ctx.author)
        await ctx.send(f"{member} has been unbanned.")

    @commands.guild_only()
    @checks.is_staff_or_perms('Mod', manage_channels=True)
    @commands.command()
    async def clear(self, ctx: commands.Context, num_messages: int, *, reason: str = None):
        """Clears messages from a chat (Mod+ or manage channels)"""
        if num_messages > 100:
            return await ctx.send("You cannot clear that many messages!")
        else:
            await ctx.channel.purge(limit=num_messages + 1)

        await self.bot.terrygon_logger.mod_logs(ctx, 'clear', ctx.channel, ctx.author, reason,
                                                num_messages=num_messages)

    @commands.guild_only()
    @checks.is_staff_or_perms("Mod", manage_channels=True)
    @commands.command()
    async def slowmode(self, ctx: commands.Context, channel: discord.TextChannel, slow_time: str, *,
                       reason: str = None):
        """Slows a channel, set slowtime to 0 to disable (Mod+ or manage channels)"""
        slow_time_seconds = common.parse_time(slow_time)
        if slow_time_seconds == -1:
            return await ctx.send("Invalid time format")

        if slow_time_seconds >= 21600:
            return await ctx.send("You cannot set a slowmode to 6 hours or higher")

        try:
            await channel.edit(slowmode_delay=slow_time_seconds)
            if slow_time != 0:
                await ctx.send(f"Slowmode of {slow_time} set to {channel.mention}")
            else:
                await ctx.send(f"Slowmode removed from {channel.mention}")
        except discord.Forbidden:
            return await ctx.send("I don't have permission to update the slowmode delay")

        await self.bot.terrygon_logger.slowmode_log(channel, slow_time, ctx.author, reason)


async def setup(bot):
    await bot.add_cog(Mod(bot))
