from datetime import datetime, timedelta
from discord.ext import commands
import discord
from discord.errors import Forbidden
import typing

from utils import checks, common, errors, paginator


class DbWarn:
    """Object representing a warn"""

    def __init__(self, id, user_id, author_id, guild_id, time_stamp, reason):
        self.id = id
        self.user_id = user_id
        self.author_id = author_id
        self.guild_id = guild_id
        self.time_stamp = time_stamp
        self.reason = reason


class Warn(commands.Cog):
    """
    Warning system
    """

    def __init__(self, bot):
        self.bot = bot

    async def warn_user_out_server(self, ctx: commands.Context, user: discord.User, reason: str or None):
        """Warns a user outside of a server."""
        warn_num = int(
            await self.bot.db.fetchval("SELECT COUNT(warn_id) FROM warns WHERE user_id = $1 AND guild_id = $2;",
                                       user.id, ctx.guild.id)) + 1
        if warn_num is None:
            warn_num = 1

        await self.bot.db.execute("INSERT INTO warns (user_id, author_id, guild_id, reason) VALUES ($1, $2, $3, $4);",
                                  user.id, ctx.author.id, ctx.guild.id, reason)
        await ctx.send(f"🚩 {user} has been warned. This is warning #{warn_num}.")
        await self.bot.terrygon_logger.mod_logs(ctx, 'warn', user, ctx.author, reason)

    @commands.guild_only()
    @checks.is_staff_or_perms("Mod", manage_roles=True, manage_channels=True)
    @commands.command(name="softwarn")
    async def soft_warn(self, ctx: commands.Context, member: typing.Union[discord.Member, int], *, reason: str = None):
        """Gives a user a warning without punishing them on 3, 4, and 5 warns (Mod+)"""
        # check if valid user
        if isinstance(member, int):
            try:
                user = await self.bot.fetch_user(member)
            except discord.NotFound:
                return await ctx.send("Invalid user given.")

            return await self.warn_user_out_server(ctx, user, reason)

        mod_bot_protection = await checks.mod_bot_protection(self.bot, ctx, member, "warn")
        if mod_bot_protection is not None:
            await ctx.send(mod_bot_protection)
            return

        async with self.bot.db.acquire() as conn:

            warn_num = int(
                await conn.fetchval("SELECT COUNT(warn_id) FROM warns WHERE user_id = $1 AND guild_id = $2;", member.id,
                                    ctx.guild.id)) + 1
            if warn_num is None:
                warn_num = 1

            await conn.execute("INSERT INTO warns (user_id, author_id, guild_id, reason) VALUES ($1, $2, $3, $4);",
                               member.id, ctx.author.id, ctx.guild.id, reason)

        await ctx.send(f"🚩 {member} has been warned. This is warning #{warn_num}.")
        await self.bot.terrygon_logger.mod_logs(ctx, 'warn', member, ctx.author, reason)

        msg = f"You have been warned on {ctx.guild.name}. "
        if reason is not None:
            msg += f"The reason is: `{reason}`. "

        msg += f"This is warning {warn_num}\n"

        try:
            await member.send(msg)
        except Forbidden:
            pass

    @commands.guild_only()
    @commands.group(name="punishments", invoke_without_command=True,
                    aliases=['punishment', 'warnpunishments', 'warnpunishment'])
    async def warn_punishments(self, ctx):
        """Commands related to setting warn punishments"""
        await ctx.send_help(ctx.command)

    @commands.guild_only()
    @warn_punishments.command()
    async def list(self, ctx: commands.Context):
        """Shows what warn will do what punishment"""
        out = discord.Embed(title=f"Warn Punishments for {ctx.guild.name}", colour=common.gen_color(ctx.guild.id))
        warn_punishment_data = await self.bot.db.fetchval(
            "SELECT warn_punishments FROM guild_settings WHERE guild_id = $1", ctx.guild.id)

        if not warn_punishment_data:
            out.description = f"There are no warn punishments on {ctx.guild.name}."
        else:
            out.description = ""
            for num, pun in warn_punishment_data.items():
                out.description += f"At **{num}** warn(s) a user will get a **{pun}**.\n"

        await ctx.send(embed=out)

    @commands.guild_only()
    @checks.is_staff_or_perms("Owner", administrator=True)
    @warn_punishments.command()
    async def set(self, ctx: commands.Context, warn_number: int, warn_punishment: str, mute_time: str = None):
        """Set punishments for warns. Valid options are `kick`, `ban`, and `mute` max number of warns allowed is 100"""
        if warn_number > 100:
            return await ctx.send("You cannot have over 100 warns")
        if warn_punishment.lower() not in ('kick', 'ban', 'mute', 'probate'):
            return await ctx.send(
                "Invalid punishment given, valid punishments are `kick`, `ban`, 'probate' and `mute`.")
        async with self.bot.db.acquire() as conn:
            if warn_punishment.lower() == 'mute':
                if await conn.fetchval("SELECT muted_role FROM roles WHERE guild_id = $1", ctx.guild.id) is None:
                    cog = self.bot.get_cog('Settings')
                    if not cog:
                        return await ctx.send(
                            "Settings cog not loaded and muted role not set, please manually set the muted role or load the setup cog to trigger the wizard")
                    await cog.muted_role_setup(ctx)

                if not mute_time:
                    mute_time = "24h"
                res = common.parse_time(mute_time)
                if res == -1:
                    return await ctx.send("Invalid time format")
                await conn.execute("UPDATE guild_settings SET warn_automute_time = $1 WHERE guild_id = $2", res,
                                   ctx.guild.id)

            if warn_punishment.lower() == 'probate':
                probate_role_id = await conn.fetchval("SELECT probation_role FROM roles WHERE guild_id = $1",
                                                      ctx.guild.id)
                probate_channel_id = await conn.fetchval("SELECT probation_channel FROM channels WHERE guild_id = $1",
                                                         ctx.guild.id)
                probation_role = ctx.guild.get_role(probate_role_id)
                if not probation_role and not probate_channel_id:
                    cog = self.bot.get_cog("Settings")
                    if not cog:
                        return await ctx.send(
                            "Settings cog not loaded and muted role not set, please manually set the muted role or load the setup cog to trigger the wizard")

                    res = await cog.probation_setup(ctx, channel=None, roles=None)
                    if res == -1:
                        return await ctx.send(
                            "Unable to set probation warn punishment due to probation configuration error.")

            if await conn.fetchval("SELECT warn_punishments FROM guild_settings WHERE guild_id = $1",
                                   ctx.guild.id) is None:
                await conn.execute(
                    "UPDATE guild_settings SET warn_punishments = json_build_object() WHERE guild_id = $1",
                    ctx.guild.id)

            await conn.execute(
                "UPDATE guild_settings SET warn_punishments = warn_punishments::jsonb || jsonb_build_object($1::INT, $2::TEXT) WHERE guild_id = $3",
                warn_number, warn_punishment, ctx.guild.id)

        await ctx.send(f"Ok, I will now {warn_punishment} when a user gets {warn_number} warn(s).")
        try:
            await self.bot.terrygon_logger.auto_mod_setup(ctx.author, warn_punishment, warn_num=warn_number)
        except errors.LoggingError:
            pass

    @commands.guild_only()
    @checks.is_staff_or_perms("Owner", administrator=True)
    @warn_punishments.command()
    async def unset(self, ctx: commands.Context, warn_number: int):
        """Unsets a warn punishment"""
        async with self.bot.db.acquire() as conn:
            if await conn.fetchval("SELECT warn_punishments->>$1 FROM guild_settings WHERE guild_id = $2", warn_number,
                                   ctx.guild.id):
                await conn.execute(
                    "UPDATE guild_settings SET warn_punishments = warn_punishments::jsonb - $1 WHERE guild_id = $2",
                    warn_number, ctx.guild.id)
                await ctx.send("Deleted warn punishment!")
            else:
                await ctx.send("No punishment is set for this warn number!")

    # handle warn punishments
    async def punish(self, member: discord.Member, warn_number: int, action: str, moderator: discord.Member = None):
        """Punishes a user for a warn"""
        bot_perms = [x[0] for x in member.guild.get_member(self.bot.user.id).guild_permissions]
        reason = f"Got {warn_number} warn(s)"
        if action.lower() == "ban" and 'ban_members' in bot_perms:
            try:
                await member.send(f"You have been banned from {member.guild.name}")
            except discord.Forbidden:
                pass

            await member.ban(reason=reason)

        elif action.lower() == "kick" and 'kick_members' in bot_perms:
            try:
                await member.send(f"You have been kicked from {member.guild.name}")
            except discord.Forbidden:
                pass

            await member.kick(reason=reason)

        elif action.lower() == "mute" and 'manage_roles' in bot_perms:
            cog = self.bot.get_cog("Mod")
            if not cog:
                msg = "Unable to auto mute member, Mod module cannot be loaded. Please contact a bot maintainer."
                await self.bot.terrygon_logger.custom_log("mod_logs", member.guild, msg)

            time_seconds = await self.bot.db.fetchval(
                "SELECT warn_automute_time FROM guild_settings WHERE guild_id = $1", member.guild.id)
            res = await cog.silent_mute_prep(member, 'timed')
            if res == -1:
                self.bot.console_output_log.warn(
                    f"Unable to auto mute user {member.id} on {member.guild.name} ({member.guild.id})")
                return
            elif res == 1:
                m_id = await self.bot.db.fetchval("SELECT id FROM mutes WHERE user_id = $1 AND guild_id = $2",
                                                  member.id,
                                                  member.guild.id)
            else:
                # if no moderator is given, the bot will take credit for the mute as the moderator responsible.
                author_id = moderator.id if moderator else self.bot.user.id
                m_id = await self.bot.db.fetchval(
                    "INSERT INTO mutes (user_id, author_id, guild_id, reason) VALUES ($1, $2, $3, $4) RETURNING id",
                    member.id, author_id, member.guild.id, reason)

            await self.bot.scheduler.add_timed_job('mute', datetime.utcnow(), timedelta(seconds=time_seconds),
                                                   action_id=m_id)

        elif action.lower() == "probate" and 'manage_roles' in bot_perms:
            cog = self.bot.get_cog("Mod")
            if not cog:
                msg = "Unable to auto mute member, Mod module cannot be loaded. Please contact a bot maintainer."
                await self.bot.terrygon_logger.custom_log("mod_logs", member.guild, msg)

            author_id = moderator.id if moderator else self.bot.user.id
            res = await cog.silent_probation(member, author_id, reason)
            if res == -1:
                self.bot.console_output_log.warn(
                    f"Unable to auto probate user ({member.id}) in {member.guild.name} ({member.guild.id})")
                return

        else:
            msg = f":bangbang: Unable to auto {action}, missing permissions."
            await self.bot.terrygon_logger.custom_log("mod_logs", member.guild, msg)

        try:
            await self.bot.terrygon_logger.auto_mod(action, member, reason)
        except errors.LoggingError:
            pass

    @commands.guild_only()
    @checks.is_staff_or_perms("Mod", manage_roles=True, manage_channels=True)
    @commands.command()
    async def warn(self, ctx: commands.Context, member: typing.Union[discord.Member, int], *, reason: str = None):
        """Warns a user, set your punishments with the `punishment set` command"""
        # check if valid user
        if isinstance(member, int):
            try:
                user = await self.bot.fetch_user(member)
            except discord.NotFound:
                return await ctx.send("Invalid user given.")

            return await self.warn_user_out_server(ctx, user, reason)

        mod_bot_protection = await checks.mod_bot_protection(self.bot, ctx, member, "warn")
        if mod_bot_protection is not None:
            await ctx.send(mod_bot_protection)
            return

        async with self.bot.db.acquire() as conn:

            warn_num = int(
                await conn.fetchval("SELECT COUNT(warn_id) FROM warns WHERE user_id = $1 AND guild_id = $2;", member.id,
                                    ctx.guild.id)) + 1
            if warn_num is None:
                warn_num = 1

            await conn.execute("INSERT INTO warns (user_id, author_id, guild_id, reason) VALUES ($1, $2, $3, $4);",
                               member.id, ctx.author.id, ctx.guild.id, reason)

            # get warn punishment data
            punishment_data = await conn.fetchval("SELECT warn_punishments FROM guild_settings WHERE guild_id = $1",
                                                  ctx.guild.id)

        await ctx.send(f"🚩 {member} has been warned. This is warning #{warn_num}.")
        try:
            await self.bot.terrygon_logger.mod_logs(ctx, 'warn', member, ctx.author, reason)
        except errors.LoggingError:
            pass

        msg = f"You have been warned on {ctx.guild.name}. "
        if reason is not None:
            msg += f"The reason is: `{reason}`. "

        msg += f"This is warning {warn_num}\n"

        if punishment_data:
            highest_punishment_value = max(punishment_data.keys())
            if str(warn_num + 1) in list(punishment_data.keys()):
                msg += f"The next warn will **{punishment_data[str(warn_num + 1)]}** you."

        try:
            await member.send(msg)
        except Forbidden:
            pass

        if punishment_data:
            if str(warn_num) in list(punishment_data.keys()):
                await self.punish(member, warn_num, punishment_data[str(warn_num)], ctx.author)

            # just in case
            elif warn_num > int(highest_punishment_value):
                await self.punish(member, warn_num, punishment_data[str(highest_punishment_value)], ctx.author)

    @commands.guild_only()
    @checks.is_staff_or_perms("Mod", manage_roles=True, manage_channels=True)
    @commands.command(name="deletewarn", aliases=["delwarn", 'unwarn'])
    async def delete_warn(self, ctx: commands.Context, member: typing.Union[discord.Member, int], warn_num: int):
        """Removes a single warn (Staff only)"""
        if isinstance(member, int):
            try:
                member = await self.bot.fetch_user(member)
            except discord.NotFound:
                return await ctx.send("Invalid user given.")

        async with self.bot.db.acquire() as conn:
            warn_records = await conn.fetch("SELECT * FROM warns WHERE user_id = $1 AND guild_id = $2", member.id,
                                            ctx.guild.id)
            if warn_records:
                deleted_warn = None
                for num, record in enumerate(warn_records, 1):
                    if num == warn_num:
                        deleted_warn = DbWarn(*record)
                        break

                if deleted_warn is None:
                    await ctx.send(f"This user does not have a warn {warn_num}")
                    return

                # just in case, should never trigger!
                if deleted_warn.guild_id != ctx.guild.id:
                    await ctx.send("You cannot clear another guild's warns!")
                    return

                await conn.execute("DELETE FROM warns WHERE warn_id = $1", deleted_warn.id)

            else:
                return await ctx.send("This user has no warns on this server!")

            await ctx.send(f"Warn {warn_num} removed!")
            await self.bot.terrygon_logger.warn_clear('clear', member, ctx.author, deleted_warn)

    @commands.guild_only()
    @commands.command(name='listwarns')
    async def list_warns(self, ctx: commands.Context, member: typing.Union[discord.Member, int] = None):
        """
        List your own warns or someone else's warns.
        Only the staff can view someone else's warns
        """
        in_server = True
        if not member:
            member = ctx.message.author

        elif isinstance(member, int):
            member = await self.bot.fetch_user(member)
            in_server = False

        has_perms = await checks.nondeco_is_staff_or_perms(ctx, self.bot.db, "Mod", manage_roles=True)

        if not has_perms and member != ctx.message.author:
            return await ctx.send("You don't have permission to list other member's warns!")

        async with self.bot.db.acquire() as conn:
            warn_records = await conn.fetch("SELECT * FROM warns WHERE user_id = $1 AND guild_id = $2", member.id,
                                            ctx.guild.id)

        if len(warn_records) == 0:
            embed = discord.Embed(color=member.color)
            embed.set_author(name=f"Warns for {member.name}#{member.discriminator}", icon_url=member.display_avatar.url)
            embed.description = "There are none!"
            return await ctx.send(embed=embed)

        user_warns = []
        for warn in warn_records:
            user_warns.append(DbWarn(*warn))

        embed = discord.Embed(color=member.color)
        embed.set_author(name=f"List of warns for {member.name}#{member.discriminator}:", icon_url=member.display_avatar.url)

        for num, warn in enumerate(user_warns, 1):
            issuer = self.bot.get_user(warn.author_id) if self.bot.get_user(
                warn.author_id) is not None else await self.bot.fetch_user(warn.author_id)

            embed.add_field(name=f"\n\n{num} : {warn.time_stamp}",
                            value=f"""{warn.reason if warn.reason is not None else 'No reason given for warn'}\n
            Warn ID: {warn.id}\nIssuer: {issuer.name}#{issuer.discriminator}""")

        if not in_server:
            embed.set_footer(text="This user is not in the server")
        await ctx.send(embed=embed)

    @commands.guild_only()
    @checks.is_staff_or_perms("Mod", manage_roles=True, manage_channels=True)
    @commands.command(name="clearwarns")
    async def clear_warns(self, ctx: commands.Context, member: typing.Union[discord.Member, int]):
        """Clear's all warns from a user"""

        if isinstance(member, int):
            try:
                member = await self.bot.fetch_user(member)
            except discord.NotFound:
                return await ctx.send("Invalid user given.")

        async with self.bot.db.acquire() as conn:
            warn_nums = await conn.fetchval("SELECT COUNT(warn_id) FROM warns WHERE user_id = $1 AND guild_id = $2",
                                            member.id, ctx.guild.id)
            if warn_nums is None:
                await ctx.send("No warns found")

            else:
                await self.bot.terrygon_logger.warn_clear('clear', member, ctx.author)
                await conn.execute("DELETE FROM warns WHERE user_id = $1 AND guild_id = $2", member.id, ctx.guild.id)
                await ctx.send(f"{warn_nums} warns cleared from {member}")


async def setup(bot):
    await bot.add_cog(Warn(bot))
