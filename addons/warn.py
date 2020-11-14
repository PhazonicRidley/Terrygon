import json

from discord.ext import commands
import discord
from discord.errors import Forbidden
import typing

from utils import checks, common, errors


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

    @commands.guild_only()
    @checks.is_staff_or_perms("Mod", manage_roles=True, manage_channels=True)
    @commands.command(name="softwarn")
    async def soft_warn(self, ctx, member: discord.Member, *, reason=None):
        """Gives a user a warning without punishing them on 3, 4, and 5 warns (Mod+)"""
        mod_bot_protection = await checks.mod_bot_protection(self.bot, ctx, member, "warn")
        if mod_bot_protection is not None:
            await ctx.send(mod_bot_protection)
            return

        async with self.bot.db.acquire() as conn:

            warn_num = int(
                await conn.fetchval("SELECT COUNT(warnID) FROM warns WHERE userid = $1 AND guildid = $2;", member.id,
                                    ctx.guild.id)) + 1
            if warn_num is None:
                warn_num = 1

            await conn.execute("INSERT INTO warns (userID, authorID, guildID, reason) VALUES ($1, $2, $3, $4);",
                               member.id, ctx.author.id, ctx.guild.id, reason)

        await ctx.send(f"🚩 {member} has been warned. This is warning #{warn_num}.")
        await self.bot.discord_logger.mod_logs(ctx, 'warn', member, ctx.author, reason)

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
    async def list(self, ctx):
        """Shows what warn will do what punishment"""
        out = discord.Embed(name=f"Warn Punishments for {ctx.guild.name}", colour=common.gen_color(ctx.guild.id))
        warn_punishment_data = await self.bot.db.fetchval(
            "SELECT warn_punishments FROM guild_settings WHERE guildid = $1", ctx.guild.id)

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
    async def set(self, ctx, warn_number: int, warn_punishment: str):
        """Set punishments for warns. Valid options are `kick`, `ban`, and `mute` max number of warns allowed is 100"""
        if warn_number > 100:
            return await ctx.send("You cannot have over 100 warns")
        print("Passed first check")
        if warn_punishment.lower() not in ('kick', 'ban', 'mute'):
            return await ctx.send("Invalid punishment given, valid punishments are `kick`, `ban`, and `mute`.")
        async with self.bot.db.acquire() as conn:
            if await conn.fetchval("SELECT warn_punishments FROM guild_settings WHERE guildid = $1",
                                   ctx.guild.id) is None:
                await conn.execute(
                    "UPDATE guild_settings SET warn_punishments = json_build_object() WHERE guildid = $1", ctx.guild.id)

            await conn.execute(
                "UPDATE guild_settings SET warn_punishments = warn_punishments::jsonb || jsonb_build_object($1::INT, $2::TEXT) WHERE guildid = $3",
                warn_number, warn_punishment, ctx.guild.id)

            if warn_punishment.lower() == 'mute' and await conn.fetchval(
                    "SELECT mutedRole FROM roles WHERE guildID = $1", ctx.guild.id) is None:
                cog = self.bot.get_cog('Setup')
                if not cog:
                    return await ctx.send(
                        "Setup cog not loaded and muted role not set, please manually set the muted role or load the setup cog to trigger the wizard")
                await cog.muted_role_setup(ctx)

        await ctx.send(f"Ok, I will now {warn_punishment} when a user gets {warn_number} warn(s).")
        try:
            await self.bot.discord_logger.auto_mod_setup(ctx.author, warn_punishment, warn_num=warn_number)
        except errors.loggingError:
            pass

    @commands.guild_only()
    @checks.is_staff_or_perms("Owner", administrator=True)
    @warn_punishments.command()
    async def unset(self, ctx, warn_number):
        """Unsets a warn punishment"""
        async with self.bot.db.acquire() as conn:
            if await conn.fetchval("SELECT warn_punishments->>$1 FROM guild_settings WHERE guildid = $2", warn_number,
                                   ctx.guild.id):
                await conn.execute(
                    "UPDATE guild_settings SET warn_punishments = warn_punishments::jsonb - $1 WHERE guildid = $2",
                    warn_number, ctx.guild.id)
                await ctx.send("Deleted warn punishment!")
            else:
                await ctx.send("No punishment is set for this warn number!")

    # handle warn punishments
    async def punish(self, ctx, member, warn_number, action):
        """Punishes a user for a warn"""

        if action.lower() == "ban":
            try:
                await member.send(f"You have been banned from {ctx.guild.name}")
            except discord.Forbidden:
                pass

            try:
                await member.ban(reason=f"Got {warn_number} warn(s)")
            except discord.Forbidden:
                return await ctx.send("Unable to ban member, check my permissions!")

        elif action.lower() == "kick":
            try:
                await member.send(f"You have been kicked from {ctx.guild.name}")

            except discord.Forbidden:
                pass
            try:
                await member.kick(reason=f"Got {warn_number} warn(s)")

            except discord.Forbidden:
                return await ctx.send("Unable to kick member, check my permissions!")

        elif action.lower() == "mute":
            async with self.bot.db.acquire() as conn:
                muted_role_id = await conn.fetchval("SELECT mutedRole FROM roles WHERE guildID = $1", ctx.guild.id)
                if muted_role_id is None:
                    return await ctx.send("No muted role found, please run the setup wizard for the muted role again")
                muted_role = ctx.guild.get_role(muted_role_id)
                if muted_role is None:
                    await conn.execute("UPDATE roles SET mutedrole = NULL WHERE guildid = $1", ctx.guild.id)
                    cog = self.bot.get_cog('Setup')
                    if not cog:
                        return await ctx.send(
                            "Set up cog not loaded and muted role not set, please manually set the muted role or load the setup cog to trigger the wizard")
                    await cog.muted_role_setup(ctx)

                try:
                    if not muted_role in member.roles or not await conn.fetchval(
                            "SELECT userID FROM mutes WHERE userID = $1 AND guildID = $2", member.id,
                            ctx.guild.id) == member.id:
                        await member.add_roles(muted_role)
                except TypeError or discord.Forbidden:
                    return await ctx.send("Unable to mute member")

                await conn.execute("INSERT INTO mutes (userID, authorID, guildID, reason) VALUES ($1, $2, $3, $4)",
                                   member.id, ctx.author.id, ctx.guild.id,
                                   f"Auto-mute for getting {warn_number} warn(s).")

                try:
                    await member.send(f"You have been muted in {ctx.guild.name}")
                except discord.Forbidden:
                    pass

        else:
            # this should never trigger!
            raise discord.errors.DiscordException("Unable to process warn punishment request")

        try:
            await self.bot.discord_logger.auto_mod(action, member, reason=f"Got {warn_number} warn(s)")
        except errors.loggingError:
            pass

    @commands.guild_only()
    @checks.is_staff_or_perms("Mod", manage_roles=True, manage_channels=True)
    @commands.command()
    async def warn(self, ctx, member: discord.Member, *, reason=None):
        """Warns a user, set your punishments with the `punishment set` command"""
        mod_bot_protection = await checks.mod_bot_protection(self.bot, ctx, member, "warn")
        if mod_bot_protection is not None:
            await ctx.send(mod_bot_protection)
            return

        async with self.bot.db.acquire() as conn:

            warn_num = int(
                await conn.fetchval("SELECT COUNT(warnID) FROM warns WHERE userid = $1 AND guildid = $2;", member.id,
                                    ctx.guild.id)) + 1
            if warn_num is None:
                warn_num = 1

            await conn.execute("INSERT INTO warns (userID, authorID, guildID, reason) VALUES ($1, $2, $3, $4);",
                               member.id, ctx.author.id, ctx.guild.id, reason)

            # get warn punishment data
            punishment_data = await conn.fetchval("SELECT warn_punishments FROM guild_settings WHERE guildid = $1",
                                                  ctx.guild.id)

        await ctx.send(f"🚩 {member} has been warned. This is warning #{warn_num}.")
        try:
            await self.bot.discord_logger.mod_logs(ctx, 'warn', member, ctx.author, reason)
        except errors.loggingError:
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
                await self.punish(ctx, member, warn_num, punishment_data[str(warn_num)])

            # just in case
            if warn_num > int(highest_punishment_value):
                await self.punish(ctx, member, warn_num, punishment_data[str(highest_punishment_value)])

    @commands.guild_only()
    @checks.is_staff_or_perms("Mod", manage_roles=True, manage_channels=True)
    @commands.command(aliases=["delwarn", 'unwarn'])
    async def deletewarn(self, ctx, member: discord.Member, warn_num: int):

        """Removes a single warn (Staff only)"""
        async with self.bot.db.acquire() as conn:
            warn_records = await conn.fetch("SELECT * FROM warns WHERE userid = $1 AND guildid = $2", member.id,
                                            ctx.guild.id)
            deleted_warn = None
            if warn_records:
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

                await conn.execute("DELETE FROM warns WHERE warnID = $1", deleted_warn.id)

            else:
                await ctx.send("This user has no warns on this server!")

            await ctx.send(f"Warn {warn_num} removed!")
            await self.bot.discord_logger.warn_clear('clear', member, ctx.author, deleted_warn)

    @commands.guild_only()
    @commands.command()
    async def listwarns(self, ctx, member: typing.Union[discord.Member, int] = None):
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

        has_perms = await checks.nondeco_is_staff_or_perms(ctx, "Mod", manage_roles=True)

        if not has_perms and member != ctx.message.author:
            return await ctx.send("You don't have permission to list other member's warns!")

        async with self.bot.db.acquire() as conn:
            warn_records = await conn.fetch("SELECT * FROM warns WHERE userid = $1 AND guildid = $2", member.id,
                                            ctx.guild.id)

        if len(warn_records) == 0:
            embed = discord.Embed(color=member.color)
            embed.set_author(name=f"Warns for {member.name}#{member.discriminator}", icon_url=member.avatar_url)
            embed.description = "There are none!"
            return await ctx.send(embed=embed)

        user_warns = []
        for warn in warn_records:
            user_warns.append(DbWarn(*warn))

        embed = discord.Embed(color=member.color)
        embed.set_author(name=f"List of warns for {member.name}#{member.discriminator}:", icon_url=member.avatar_url)

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
    @commands.command()
    async def clearwarns(self, ctx, member: typing.Union[discord.Member, int]):
        """Clear's all warns from a user"""

        if isinstance(member, int):
            member = await self.bot.fetch_user(member)

        async with self.bot.db.acquire() as conn:
            warn_nums = await conn.fetchval("SELECT COUNT(warnid) FROM warns WHERE userID = $1 AND guildID = $2",
                                            member.id, ctx.guild.id)
            if warn_nums is None:
                await ctx.send("No warns found")

            else:
                await self.bot.discord_logger.warn_clear('clear', member, ctx.author)
                await conn.execute("DELETE FROM warns WHERE userID = $1 AND guildid = $2", member.id, ctx.guild.id)
                await ctx.send(f"{warn_nums} warns cleared from {member.name}")


def setup(bot):
    bot.add_cog(Warn(bot))
