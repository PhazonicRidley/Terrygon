from discord.ext import commands
import discord
from discord.errors import Forbidden
import typing

from utils import checks


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

    @checks.is_staff_or_perms("Mod", manage_roles=True, manage_channels=True)
    @commands.guild_only()
    @commands.command()
    async def softwarn(self, ctx, member: discord.Member, *, reason=None):
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

    @checks.is_staff_or_perms("Mod", manage_roles=True, manage_channels=True)
    @commands.guild_only()
    @commands.command()
    async def warn(self, ctx, member: discord.Member, *, reason=None):
        """Warns a user, at 3 and 4 warns kick, on 5 warns, ban"""
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

        if warn_num == 2:
            msg += "The next warning will **kick** you"
            try:
                await member.send(msg)
            except Forbidden:
                pass

        elif warn_num == 3:
            msg += f"You have been kicked from {ctx.guild.name} for getting 3 warns. The next warning will also **kick** you"
            await self.bot.discord_logger.auto_mod('kick', member,
                                                 f"Warn 3: `{reason if reason is not None else 'No reason given for warn'}`")
            try:
                await member.send(msg)
            except Forbidden:
                pass
            await member.kick(reason=f"Warn 3: `{reason}`")

        elif warn_num == 4:
            msg += f"You have been kicked from {ctx.guild.name} for getting 4 warns. The next warning will **ban** you"
            await self.bot.discord_logger.auto_mod('kick', member,
                                                 f"Warn 4: `{reason if reason is not None else 'No reason given for warn'}`")
            try:
                await member.send(msg)
            except Forbidden:
                pass

            await member.kick(reason=f"Warn 4: `{reason}`")

        elif warn_num >= 5:
            msg += f"You have been banned from {ctx.guild.name} for getting {warn_num} warns."
            await self.bot.discord_logger.auto_mod('ban', member,
                                                 f"Warn 5: `{reason if reason is not None else 'No reason given for warn'}`")
            try:
                await member.send(msg)
            except Forbidden:
                pass

            await member.ban(reason=f"Warn 5: `{reason}`")

        else:
            try:
                await member.send(msg)
            except Forbidden:
                pass

    @checks.is_staff_or_perms("Mod", manage_roles=True, manage_channels=True)
    @commands.guild_only()
    @commands.command(aliases=["delwarn", 'unwarn'])
    async def deletewarn(self, ctx, member: discord.Member, warn_num: int):

        """Removes a single warn (Staff only)"""
        async with self.bot.db.acquire() as conn:
            warn_records = await conn.fetch("SELECT * FROM warns WHERE userid = $1 AND guildid = $2", member.id, ctx.guild.id)
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
            await self.bot.discord_logger.warn_clear(ctx, 'clear', member, ctx.author, deleted_warn)

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
            warn_records = await conn.fetch("SELECT * FROM warns WHERE userid = $1 AND guildid = $2", member.id, ctx.guild.id)

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

    @checks.is_staff_or_perms("Mod", manage_roles=True, manage_channels=True)
    @commands.guild_only()
    @commands.command()
    async def clearwarns(self, ctx, member: typing.Union[discord.Member, int]):
        """Clear's all warns from a user"""

        if isinstance(member, int):
            member = await self.bot.fetch_user(member)

        async with self.bot.db.acquire() as conn:
            warn_nums = await conn.fetchval("SELECT COUNT(warnid) FROM warns WHERE userID = $1 AND guildID = $2", member.id, ctx.guild.id)
            if warn_nums is None:
                await ctx.send("No warns found")

            else:
                await self.bot.discord_logger.warn_clear(ctx, 'clear', member, ctx.author)
                await conn.execute("DELETE FROM warns WHERE userID = $1 AND guildid = $2", member.id, ctx.guild.id)
                await ctx.send(f"{warn_nums} warns cleared from {member.name}")


def setup(bot):
    bot.add_cog(Warn(bot))
