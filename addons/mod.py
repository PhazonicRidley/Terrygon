import discord
from discord.ext import commands, flags
from logzero import setup_logger
import typing
from utils import checks, common, errors
from datetime import datetime, timedelta

# set up logging instance
mod_console_logger = setup_logger(name='mod command logs', logfile='logs/mod.log', maxBytes=1000000)


class Mod(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    # mute commands
    async def mute_prep(self, ctx, member, mode: str):
        """Sets up the mute commands"""
        mod_bot_protection = await checks.mod_bot_protection(self.bot, ctx, member, "mute")
        if mod_bot_protection is not None:
            await ctx.send(mod_bot_protection)
            return -1

        async with self.bot.db.acquire() as conn:
            muted_role_id = await conn.fetchval("SELECT mutedRole FROM roles WHERE guildID = $1", ctx.guild.id)
            if muted_role_id is None:
                cog = self.bot.get_cog('Setup')
                if not cog:
                    return await ctx.send(
                        "Set up cog not loaded and muted role not set, please manually set the muted role or load the setup cog to trigger the wizard. Or if you have an existing muted role. run `mutedrole set <role>` to set your muted role to the bot.")
                await cog.muted_role_setup(ctx)

            muted_role_id = await conn.fetchval("SELECT mutedRole FROM roles WHERE guildID = $1", ctx.guild.id)
            if muted_role_id is None:
                await ctx.send("No muted role found, please run the setup wizard for the muted role again")
                return -1

            muted_role = ctx.guild.get_role(muted_role_id)
            if muted_role is None:
                await conn.execute("UPDATE roles SET mutedrole = NULL WHERE guildid = $1", ctx.guild.id)
                cog = self.bot.get_cog('Setup')
                if not cog:
                    await ctx.send(
                        "Set up cog not loaded and muted role not set, please manually set the muted role or load the setup cog to trigger the wizard")
                await cog.muted_role_setup(ctx)
                return -1

            try:
                if muted_role in member.roles or await conn.fetchval(
                        "SELECT userID FROM mutes WHERE userID = $1 AND guildID = $2", member.id,
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
                await ctx.send("💢 I dont have permission to do this.")
                return -1

            return 0

    @commands.guild_only()
    @checks.is_staff_or_perms("Mod", manage_roles=True)
    @commands.command()
    async def mute(self, ctx, member: discord.Member, *, reason: str = None):
        res = await self.mute_prep(ctx, member, 'normal')
        """Mutes a member so they cannot speak in the server. (Mod+, manage_roles)"""
        if res == -1:
            return

        await self.bot.db.execute("INSERT INTO mutes (userID, authorID, guildID, reason) VALUES ($1, $2, $3, $4)",
                                  member.id, ctx.author.id, ctx.guild.id, reason)

        msg = f"You have been muted in {ctx.guild.name}"
        if reason is not None:
            msg += f" for the following reason: {reason}"

        try:
            await member.send(msg)
        except discord.Forbidden:
            pass
        await self.bot.discord_logger.mod_logs(ctx, 'mute', member, ctx.author, reason)

        await ctx.send(f"{member} has been muted.")

    @commands.guild_only()
    @checks.is_staff_or_perms("Mod", manage_roles=True)
    @commands.command()
    async def timemute(self, ctx, member: discord.Member, time: str, *, reason: str = None):
        """Mutes a member for a limited number of time (Use dhms format, for example `5m` would be 5 minutes) (Mod+)"""
        time_seconds = common.parse_time(time)
        if time_seconds == -1:
            return await ctx.send("Invalid time passed, please make sure its in the dhms format.")

        res = await self.mute_prep(ctx, member, 'timed')
        if res == -1:
            return
        elif res == 1:
            m_id = await self.bot.db.fetchval("SELECT id FROM mutes WHERE userid = $1 AND guildid = $2", member.id,
                                              ctx.guild.id)
        else:
            m_id = await self.bot.db.fetchval(
                "INSERT INTO mutes (userID, authorID, guildID, reason) VALUES ($1, $2, $3, $4) RETURNING id",
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
            await self.bot.discord_logger.timed_mod_logs('mute', member, ctx.author, ts, reason)
        except errors.loggingError:
            pass

        await self.bot.scheduler.add_timed_job('mute', datetime.utcnow(), timedelta(seconds=time_seconds),
                                               action_id=m_id)

    @commands.guild_only()
    @checks.is_staff_or_perms("Mod", manage_roles=True)
    @commands.command()
    async def unmute(self, ctx, member: discord.Member):
        """Unmutes a member so they can speak again. (Mod+, manage_roles)"""
        mod_bot_protection = await checks.mod_bot_protection(self.bot, ctx, member, "unmute")
        if mod_bot_protection is not None:
            await ctx.send(mod_bot_protection)
            return

        async with self.bot.db.acquire() as conn:
            muted_role_id = (await conn.fetchrow("SELECT mutedRole FROM roles WHERE guildID = $1", ctx.guild.id))[0]
            if muted_role_id is None:
                cog = self.bot.get_cog('Setup')
                if not cog:
                    return await ctx.send(
                        "Set up cog not loaded and muted role not set, please manually set the muted role or load the setup cog to trigger the wizard")
                await cog.muted_role_setup(ctx)

            muted_role = ctx.guild.get_role(muted_role_id)
            if muted_role is None:
                cog = self.bot.get_cog('Setup')
                if not cog:
                    return await ctx.send(
                        "Set up cog not loaded and muted role not set, please manually set the muted role or load the setup cog to trigger the wizard")
                await cog.muted_role_setup(ctx)

            try:
                if not muted_role in member.roles and not await conn.fetchval(
                        "SELECT userID FROM mutes WHERE userID = $1 AND guildID = $2", member.id,
                        ctx.guild.id) == member.id:
                    await ctx.send("User is not muted")
                    return
            except TypeError:
                pass

            try:
                await member.remove_roles(muted_role)
            except discord.Forbidden:
                await ctx.send("💢 I dont have permission to do this.")
                return

            await conn.execute("DELETE FROM mutes WHERE userID = $1 AND guildID = $2", member.id, ctx.guild.id)

            await self.bot.discord_logger.mod_logs(ctx, 'unmute', member, ctx.author)

            await ctx.send(f"{member} has been unmuted.")

    # lockdown commands
    @commands.guild_only()
    @checks.is_staff_or_perms("Mod", manage_channels=True)
    @flags.add_flag("--channel", "-c", type=discord.TextChannel, default=None)
    @flags.add_flag("--reason", '-r', type=str, default="", nargs="+")
    @flags.command(aliases=['lock'], )
    async def lockdown(self, ctx, **flag_args):
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
            await ctx.send(f"{self.bot.discord_logger.emotes['lock']} {channel.mention} has been locked.")

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

        channel_lock_msg = f"{self.bot.discord_logger.emotes['lock']} Channel locked."
        reason = None
        if flag_args['reason']:
            reason = ' '.join(flag_args['reason'])
        if reason:
            channel_lock_msg += f" The reason is `{reason}`"
        if error_string:
            channel_lock_msg += f" But, {error_string}"
        await channel.send(channel_lock_msg)
        await self.bot.discord_logger.mod_logs(ctx, "lock", channel, ctx.author, reason)

    @commands.guild_only()
    @checks.is_staff_or_perms("Mod", manage_channels=True)
    @flags.add_flag("--channel", '-c', type=discord.TextChannel, default=None)
    @flags.command(aliases=['unlock'], )
    async def unlockdown(self, ctx, **flag_args):
        """Unlocks a channel, -c flag is not needed for unlocking the channel the command is invoked in"""

        staff_roles = await common.get_staff_roles(ctx)
        channel = flag_args['channel']
        if channel is None:
            channel = ctx.channel
        else:
            await ctx.send(f"{self.bot.discord_logger.emotes['unlock']} {channel.mention} has been unlocked.")

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
                        "SELECT mutedrole FROM roles WHERE guildid = $1", ctx.guild.id):
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

        channel_lock_msg = f"{self.bot.discord_logger.emotes['unlock']} Channel unlocked."
        if error_string:
            channel_lock_msg += f" But, {error_string}"
        await channel.send(channel_lock_msg)
        await self.bot.discord_logger.mod_logs(ctx, "unlock", channel, ctx.author)

    # kick and ban commands

    async def remove_from_approval_list(self, member: discord.Member, guild: discord.Guild):
        async with self.bot.db.acquire() as conn:
            if not await conn.fetchval("SELECT approvalsystem FROM guild_settings WHERE guildid = $1", guild.id):
                return
            else:
                if not await conn.fetchval("SELECT * FROM approvedmembers WHERE guildid = $1 AND userid = $2", guild.id,
                                           member.id):
                    return
                else:
                    await conn.fetchval("DELETE FROM approvedmembers WHERE userid = $1 AND guildid = $2", member.id,
                                        guild.id)

    @commands.guild_only()
    @checks.is_staff_or_perms("Mod", kick_members=True)
    @commands.command()
    async def kick(self, ctx, member: discord.Member, *, reason: str = None):
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

        await ctx.send(f"{member.name}#{member.discriminator} has been kicked {self.bot.discord_logger.emotes['kick']}")
        await self.bot.discord_logger.mod_logs(ctx, 'kick', member, ctx.author, reason)

    async def ban_prep(self, ctx, member, mode, **kwargs):
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
    async def ban(self, ctx, member: typing.Union[discord.Member, int], *, reason: str = None):
        """Ban a member. (Admin+)"""
        user = await self.ban_prep(ctx, member, 'normal', reason=reason)
        if not user:
            return

        try:
            await ctx.guild.ban(user, reason=reason if reason is not None else "No reason given", delete_message_days=0)
        except discord.Forbidden:
            await ctx.send("I am unable to ban, check permissions!")
            return

        await ctx.send(f"{user.name}#{user.discriminator} has been banned {self.bot.discord_logger.emotes['ban']}")
        await self.bot.discord_logger.mod_logs(ctx, 'ban', user, ctx.author, reason)

    @commands.guild_only()
    @checks.is_staff_or_perms("Admin", ban_members=True)
    @commands.command(aliases=['unyeet'])
    async def unban(self, ctx, member: typing.Union[discord.Member, int], *, reason: str = None):
        """Unban a person. (Admin+)"""
        user = await self.ban_prep(ctx, member, 'normal', reason=reason)
        if not user:
            return

        try:
            await ctx.guild.unban(user, reason=reason if reason is not None else "No reason given")
        except discord.Forbidden:
            await ctx.send("I am unable to unban, check permissions!")
            return

        await ctx.send(f"{user.name}#{user.discriminator} has been unbanned {self.bot.discord_logger.emotes['unban']}")
        await self.bot.discord_logger.mod_logs(ctx, 'unban', user, ctx.author, reason)

    @commands.guild_only()
    @checks.is_staff_or_perms("Admin", ban_members=True)
    @commands.command()
    async def timeban(self, ctx, member: discord.Member, time: str, *, reason: str = None):
        """Bans a user for a limited amount of time. Time must be in dhms format: (example: 5m is 5 minutes)(Admin+ or ban perms)"""
        time_seconds = common.parse_time(time)
        if time_seconds == -1:
            return await ctx.send("Invalid time passed, please make sure its in the dhms format.")
        ts = (datetime.utcnow() + timedelta(seconds=time_seconds))
        user = await self.ban_prep(ctx, member, 'timed', timestamp=ts, reason=reason)
        if not user:
            return
        try:
            await ctx.guild.ban(user, reason=reason if reason else "No reason given")
        except discord.Forbidden:
            return await ctx.send("I am unable to ban, check permissions!")
        if reason:
            query = "INSERT INTO bans (userid, authorid, guildid, reason) VALUES ($1, $2, $3, $4) RETURNING id"
            args = [user.id, ctx.author.id, ctx.guild.id, reason]
        else:
            query = "INSERT INTO bans (userid, authorid, guildid) VALUES ($1, $2, $3) RETURNING id"
            args = [user.id, ctx.author.id, ctx.guild.id]

        b_id = await self.bot.db.fetchval(query, *args)
        await ctx.send(
            f"{user} has been banned until {ts.strftime('%Y-%m -%d %H:%M:%S')} {self.bot.discord_logger.emotes['ban']}")
        try:
            await self.bot.discord_logger.timed_mod_logs("ban", user, ctx.author, ts, reason)
        except errors.loggingError:
            pass

        await self.bot.scheduler.add_timed_job("ban", datetime.utcnow(), timedelta(seconds=time_seconds),
                                               action_id=b_id)

    @commands.guild_only()
    @checks.is_staff_or_perms("Admin", ban_members=True)
    @commands.command()
    async def softban(self, ctx, member: typing.Union[discord.Member, int], *, reason: str = None):

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

        await self.bot.db.execute("INSERT INTO bans (userID, authorid, guildID, reason) VALUES ($1, $2, $3, $4)",
                                  member.id, ctx.author.id, ctx.guild.id, reason)

        await ctx.send(
            f"{member.name}#{member.discriminator} has been softbanned {self.bot.discord_logger.emotes['ban']}")
        await self.bot.discord_logger.mod_logs(ctx, 'softban', member, ctx.author, reason)

    @commands.guild_only()
    @checks.is_staff_or_perms("Admin", ban_members=True)
    @commands.command()
    async def unsoftban(self, ctx, user: int):
        member = await self.bot.fetch_user(user)
        if member is None:
            return await ctx.send("User does not exist")
        async with self.bot.db.acquire() as conn:
            if await conn.fetchval("SELECT * FROM bans WHERE userid = $1 AND guildid = $2", member.id, ctx.guild.id):
                await conn.execute("DELETE FROM bans WHERE userid = $1 AND guildid = $2",
                                   member.id, ctx.guild.id)
            else:
                return await ctx.send("User is not softbanned")

        await ctx.send(
            f"{member.name}#{member.discriminator} has been unsoftbanned {self.bot.discord_logger.emotes['warn']}")

        await self.bot.discord_logger.unsoftban_log(ctx, member)

    @commands.guild_only()
    @checks.is_staff_or_perms('Mod', manage_channels=True)
    @commands.command()
    async def clear(self, ctx, num_messages: int, *, reason: str = None):
        """Clears messages from a chat (Mod+ or manage channels)"""
        if num_messages > 100:
            return await ctx.send("You cannot clear that many messages!")
        else:
            await ctx.channel.purge(limit=num_messages + 1)

        await self.bot.discord_logger.mod_logs(ctx, 'clear', ctx.channel, ctx.author, reason, num_messages=num_messages)

    @commands.guild_only()
    @checks.is_staff_or_perms("Mod", manage_channels=True)
    @commands.command()
    async def slowmode(self, ctx, channel: discord.TextChannel, slow_time, *, reason=None):
        """Slows a channel, set slowtime to 0 to disable (Mod+ or manage channels)"""
        slow_time_seconds = common.parse_time(slow_time)
        if slow_time_seconds == -1:
            return await ctx.send("Invalid time format")

        if slow_time_seconds >= 21600:
            return await ctx.send("You cannot set a slowmode to 6 hours or higher")

        try:
            await channel.edit(slowmode_delay=slow_time_seconds)
            await ctx.send(f"Slowmode of {slow_time} set to {channel.mention}")
        except discord.Forbidden:
            return await ctx.send("I don't have permission to update the slowmode delay")

        await self.bot.discord_logger.slowmode_log(channel, slow_time, ctx.author, reason)


def setup(bot):
    bot.add_cog(Mod(bot))
