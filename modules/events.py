import discord
from discord.ext import commands
from utils import checks


class Events(commands.Cog):
    """
    Events for the bot
    """

    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_user_update(self, before: discord.User, after: discord.User):
        if before.name != after.name:
            await self.bot.terrygon_logger.user_update("username", after, before.name, after.name)

        if before.discriminator != after.discriminator:
            await self.bot.terrygon_logger.user_update("discriminator", after, before.discriminator,
                                                       after.discriminator)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        # makes sure logging is set up
        if not await self.bot.is_log_registered(after.guild, "member_logs"):
            return

        if before.nick != after.nick:
            await self.bot.terrygon_logger.member_update("nickname", after, before.nick, after.nick)

        # role changes
        if len(before.roles) > len(after.roles):
            await self.bot.terrygon_logger.role_update("remove role", before, after)
        elif len(after.roles) > len(before.roles):
            await self.bot.terrygon_logger.role_update("add role", before, after)

    async def add_guild(self, new_guild):
        async with self.bot.db.acquire() as conn:
            schema_list = ['channels', 'roles', 'guild_settings', 'trusted_users', 'color_settings']
            for table in schema_list:
                try:
                    await conn.execute(f"INSERT INTO {table} (guild_id) VALUES ($1)", new_guild.id)
                except Exception:
                    pass

    # join leave logs
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if not await self.bot.is_log_registered(member.guild, "member_logs"):
            logs = False

        else:
            logs = True

        async with self.bot.db.acquire() as conn:

            # check if member is approved if needed
            if await conn.fetchval("SELECT approval_system FROM guild_settings WHERE guild_id = $1", member.guild.id):
                if await conn.fetchval("SELECT user_id FROM approved_members WHERE user_id = $1 AND guild_id = $2",
                                       member.id, member.guild.id):
                    try:
                        approved_role = member.guild.get_role(
                            await conn.fetchval("SELECT approved_role FROM roles WHERE guild_id = $1", member.guild.id))
                        await member.add_roles(approved_role)
                    except Exception:
                        pass

            # check for softbans
            if await conn.fetchval("SELECT user_id FROM bans WHERE user_id = $1 AND guild_id = $2",
                                   member.id, member.guild.id):
                try:
                    issuer_id = await conn.fetchval("SELECT author_id FROM bans WHERE user_id = $1 AND guild_id = $2",
                                                    member.id, member.guild.id)
                    reason = await conn.fetchval("SELECT reason FROM bans WHERE user_id = $1 AND guild_id = $2",
                                                 member.id, member.guild.id)
                except TypeError:
                    reason = None

                dm_msg = f"You have been softbanned from {member.guild.name}"
                if reason:
                    dm_msg += f" For the reason {reason}"
                try:
                    await member.send(dm_msg)
                except discord.Forbidden:
                    reason += " `Message not sent to user`"

                if logs:
                    await self.bot.terrygon_logger.softban_join(member,
                                                                self.bot.get_user(issuer_id) if self.bot.get_user(
                                                                    issuer_id) is not None else await self.bot.fetch_user(
                                                                    issuer_id), reason)

                try:
                    await member.kick(
                        reason="softban" + f", the reason is: {reason!r}" if reason is not None else "No reason")
                    return
                except discord.Forbidden:
                    self.bot.console_output.warning(
                        f"Unable to kick user in softban join on {member.guild.name}, check perms")

            # check if member is muted
            try:
                muted_id, reason = await conn.fetchrow(
                    "SELECT id, reason FROM mutes WHERE user_id = $1 AND guild_id = $2",
                    member.id, member.guild.id)
            except TypeError:
                muted_id = None

            if muted_id:
                muted_role_id = await conn.fetchval("SELECT muted_role FROM roles WHERE guild_id = $1", member.guild.id)
                muted_role = member.guild.get_role(muted_role_id)
                if not muted_role_id or not muted_role:
                    return

                await member.add_roles(muted_role,
                                       reason=f"User muted for the reason {reason!r} on join." if reason else "User muted on join.")

            # check if member is probated and for auto probation.
            probation_role_id = await conn.fetchval("SELECT probation_role FROM roles WHERE guild_id = $1",
                                                    member.guild.id)
            probation_role = member.guild.get_role(probation_role_id)

            auto_probate = await conn.fetchval("SELECT auto_probate FROM guild_settings WHERE guild_id = $1",
                                               member.guild.id)
            probated_id = await conn.fetchrow("SELECT id FROM probations WHERE guild_id = $1 AND user_id = $2",
                                              member.guild.id, member.id)
            if auto_probate and not probated_id and probation_role_id and probation_role:
                await conn.execute(
                    "INSERT INTO probations (user_id, author_id, guild_id, reason) VALUES ($1, $2, $3, 'Auto probate')",
                    member.id, self.bot.user.id, member.guild.id)

            probated_id, reason = await conn.fetchrow(
                "SELECT id, reason FROM probations WHERE user_id = $1 AND guild_id = $2", member.id, member.guild.id)

            if probation_role_id and probation_role and probated_id:
                await member.add_roles(probation_role,
                                       reason=f"User probated for the reason {reason!r} on join." if reason else "User probated on join.")

            # logs join
            if await conn.fetchval("SELECT enable_join_leave_logs FROM guild_settings WHERE guild_id = $1",
                                   member.guild.id) and logs:
                await self.bot.terrygon_logger.join_leave_logs("join", member)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        if not await self.bot.is_log_registered(member.guild, "member_logs"):
            return

        if await self.bot.db.fetchval("SELECT enable_join_leave_logs FROM guild_settings WHERE guild_id = $1",
                                      member.guild.id):
            await self.bot.terrygon_logger.join_leave_logs("left", member)

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User):
        """Called when user gets banned"""
        probation_id = await self.bot.db.fetchval("SELECT id FROM probations WHERE guild_id = $1 AND user_id = $2",
                                                  guild.id, user.id)
        muted_id = await self.bot.db.fetchval("SELECT id FROM mutes WHERE guild_id = $1 AND user_id = $2", guild.id,
                                              user.id)
        if probation_id:
            await self.bot.db.execute("DELETE FROM probations WHERE id = $1", probation_id)
            self.bot.console_output_log.info(
                f"Removed probation for user: {user.id} ({user}) on guild {guild.id} ({guild}) due to ban")

        if muted_id:
            await self.bot.execute("DELETE FROM mutes WHERE id = $1", muted_id)
            self.bot.console_output_log.info(
                f"Removed probation for user: {user.id} ({user}) on guild {guild.id} ({guild}) due to ban")

    # message logs
    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if not await self.bot.is_log_registered(after.guild, "message_logs"):
            return

        if before.content == after.content:
            return

        if after.author.bot:
            return

        if await self.bot.db.fetchval("SELECT enable_core_message_logs FROM guild_settings WHERE guild_id = $1",
                                      after.guild.id):
            await self.bot.terrygon_logger.message_edit_logs("msgedit", before, after)

    @commands.Cog.listener()
    async def on_message_delete(self, message):
        if not await self.bot.is_log_registered(message.guild, "message_logs"):
            return

        if await self.bot.db.fetchval("SELECT enable_core_message_logs FROM guild_settings WHERE guild_id = $1",
                                      message.guild.id):
            await self.bot.terrygon_logger.message_deletion("mdelete", message)

    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        await self.add_guild(guild)

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel):
        muted_role = await self.bot.db.fetchval("SELECT muted_role FROM roles WHERE guild_id = $1", channel.guild.id)
        muted_role = channel.guild.get_role(muted_role)
        if not muted_role:
            return
        kwargs = {
            'send_messages': False
        }

        if isinstance(channel, discord.CategoryChannel):
            kwargs.update({'connect': False})
        elif isinstance(channel, discord.VoiceChannel):
            del kwargs['send_messages']
            kwargs.update({'connect': False})

        try:
            channel.overwrites[muted_role]
        except KeyError:
            try:
                await channel.set_permissions(muted_role, **kwargs)
            except discord.Forbidden:
                return

        if await self.bot.db.fetchval("SELECT approval_system FROM guild_settings WHERE guild_id = $1",
                                      channel.guild.id):
            approval_role = channel.guild.get_role(
                await self.bot.db.fetchval("SELECT approved_role FROM roles WHERE guild_id = $1", channel.guild.id))
            if not approval_role:
                return

            if channel.overwrites_for(channel.guild.default_role).read_messages is not False:
                try:
                    await channel.set_permissions(approval_role, read_messages=True)
                    await channel.set_permissions(channel.guild.default_role, read_messages=False)
                except discord.Forbidden:
                    return

    @checks.is_bot_owner()
    @commands.command(name="autoguildadd")
    async def auto_guild_add(self, ctx: commands.Context):
        """Automatically tries to add every guild the bot is in to the database, if they're already in there, nothing happens (Bot owner only)"""
        for guild in self.bot.guilds:
            await self.add_guild(guild)
        await ctx.send("Added all guilds to the database!")

    @checks.is_bot_owner()
    @commands.command(name="manualguildadd")
    async def manual_guild_add(self, ctx: commands.Context, new_guild_id: int):
        """Manually adds a guild to the database (Bot owner only)"""
        new_guild = await self.bot.fetch_guild(new_guild_id)
        if new_guild is None:
            return await ctx.send("Invalid guild.")

        await self.add_guild(new_guild)
        await ctx.send(f"Guild {new_guild.name} added to the database manually")

    @checks.is_bot_owner()
    @commands.command(name="manualguildremove")
    async def manual_guild_remove(self, ctx: commands.Context, guild_id: int):
        """Fully removes a guild and its data (Bot owner only)"""
        guild = await self.bot.fetch_guild(guild_id)
        async with self.bot.db.acquire() as conn:
            schema_list = await conn.fetchrow("SELECT table_name FROM information_schema.columns WHERE column_name = 'guild_id'")
            for table in schema_list:
                try:
                    await conn.execute(f"DELETE FROM {table} WHERE guild_id = $1", guild.id)
                except Exception:
                    pass

        await ctx.send(f"Guild {guild.name} removed")

    @checks.is_staff_or_perms("Admin", manage_server=True)
    @commands.command(name="autoprobate")
    async def auto_probate(self, ctx: commands.Context, option: str = None):
        """Enables or disables autoprobate (system to automatically probate users on join)
        - type `enable`, `on`, or `1` to turn on.
        - type `disable`, `off`, or `0` to turn off.
        To get status of auto probate, do not specify an option.
        Must have set probation system with role and channel set up.
        """
        role_id = await self.bot.db.fetchval("SELECT probation_role FROM roles WHERE guild_id = $1", ctx.guild.id)
        channel_id = await self.bot.db.fetchval("SELECT probation_channel FROM channels WHERE guild_id = $1",
                                                ctx.guild.id)
        role = ctx.guild.get_role(role_id)
        channel = ctx.guild.get_channel(channel_id)
        if not role_id or not channel:
            cog = self.bot.get_cog("Settings")
            if not cog:
                msg = "Settings cog not loaded and muted role not set, please manually set the muted role or load the setup cog to trigger the wizard"
                self.bot.error_log.error(f"Guild: {ctx.guild.id}" + msg)
                return await ctx.send(msg)

            res = await cog.probate_setup(ctx, channel=None, role=None)
            if res == -1:
                return await ctx.send("Unable to set auto probate because probation is not properly configured.")

        status = await self.bot.db.fetchval("SELECT auto_probate FROM guild_settings WHERE guild_id = $1", ctx.guild.id)

        if option is None:
            if status:
                return await ctx.send("Auto probate is currently enabled. To disable, please run `autoprobate disable`")
            else:
                return await ctx.send("Auto probate is currently disabled. To enable, please run `autoprobate enable`")

        if option.lower() in ("enable", "on", "1"):
            if status:
                return await ctx.send("Auto probate already enabled. Use `disable`, `off`, or `0` to disable.")
            await self.bot.db.execute("UPDATE guild_settings SET auto_probate = TRUE WHERE guild_id = $1", ctx.guild.id)
            msg = ":warning: **Auto probate has been enabled.**"
            await ctx.send(msg)

        elif option.lower() in ("disable", "off", "0"):
            if not status:
                return await ctx.send("Auto probate is disabled. Use `enable`, `on`, or `1` to enable")

            await self.bot.db.execute("UPDATE guild_settings SET auto_probate = FALSE WHERE guild_id = $1",
                                      ctx.guild.id)
            msg = ":white_check_mark: **Auto probate has been disabled.**"
            await ctx.send(msg)

        else:
            await ctx.send("Invalid option given.")
            return await ctx.send_help(ctx.command)

        await self.bot.terrygon_logger.custom_log("mod_logs", ctx.guild, msg + f"\nBy {ctx.author.mention} ({ctx.author.id})")


async def setup(bot):
    await bot.add_cog(Events(bot))
