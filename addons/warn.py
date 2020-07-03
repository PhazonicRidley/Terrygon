from discord.ext import commands
import discord
from discord.errors import Forbidden
import asyncpg
import typing

from utils import checks, errors


class DbWarns():
    """Object repersenting a warn"""

    def __init__(self, dbRecord: asyncpg.Record):
        self.id = dbRecord[0]
        self.userid = dbRecord[1]
        self.authorid = dbRecord[2]
        self.guildid = dbRecord[3]
        self.time_stamp = dbRecord[4]
        self.reason = dbRecord[5]


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
        modandbotprotection = await checks.modAndBotProtection(self.bot, ctx, member, "warn")
        if modandbotprotection is not None:
            await ctx.send(modandbotprotection)
            return

        async with self.bot.db.acquire() as conn:

            numOfWarns = int(await conn.fetchval("SELECT COUNT(warnID) FROM warns WHERE userid = $1 AND guildid = $2;", member.id, ctx.guild.id)) + 1
            if numOfWarns is None:
                numOfWarns = 1

            await conn.execute("INSERT INTO warns (userID, authorID, guildID, reason) VALUES ($1, $2, $3, $4);",
                               member.id, ctx.author.id, ctx.guild.id, reason)

        await ctx.send(f"🚩 {member} has been warned. This is warning #{numOfWarns}.")
        await self.bot.discordLogger.modlogs(ctx, 'warn', member, ctx.author, reason)

        msg = f"You have been warned on {ctx.guild.name}. "
        if reason is not None:
            msg += f"The reason is: `{reason}`. "

        msg += f"This is warning {numOfWarns}\n"

        try:
            await member.send(msg)
        except Forbidden:
            pass

    @checks.is_staff_or_perms("Mod", manage_roles=True, manage_channels=True)
    @commands.guild_only()
    @commands.command()
    async def warn(self, ctx, member: discord.Member, *, reason=None):
        """Warns a user, at 3 and 4 warns kick, on 5 warns, ban"""
        modandbotprotection = await checks.modAndBotProtection(self.bot, ctx, member, "warn")
        if modandbotprotection is not None:
            await ctx.send(modandbotprotection)
            return

        async with self.bot.db.acquire() as conn:

            numOfWarns = int(
                await conn.fetchval("SELECT COUNT(warnID) FROM warns WHERE userid = $1 AND guildid = $2;", member.id,
                                    ctx.guild.id)) + 1
            if numOfWarns is None:
                numOfWarns = 1

            await conn.execute("INSERT INTO warns (userID, authorID, guildID, reason) VALUES ($1, $2, $3, $4);",
                               member.id, ctx.author.id, ctx.guild.id, reason)

        await ctx.send(f"🚩 {member} has been warned. This is warning #{numOfWarns}.")
        await self.bot.discordLogger.modlogs(ctx, 'warn', member, ctx.author, reason)

        msg = f"You have been warned on {ctx.guild.name}. "
        if reason is not None:
            msg += f"The reason is: `{reason}`. "

        msg += f"This is warning {numOfWarns}\n"

        if numOfWarns == 2:
            msg += "The next warning will **kick** you"
            try:
                await member.send(msg)
            except Forbidden:
                pass

        elif numOfWarns == 3:
            msg += f"You have been kicked from {ctx.guild.name} for getting 3 warns. The next warning will also **kick** you"
            await self.bot.discordLogger.automod('kick', member,
                                                 f"Warn 3: `{reason if reason is not None else 'No reason given for warn'}`")
            try:
                await member.send(msg)
            except Forbidden:
                pass
            await member.kick(reason=f"Warn 3: `{reason}`")

        elif numOfWarns == 4:
            msg += f"You have been kicked from {ctx.guild.name} for getting 4 warns. The next warning will **ban** you"
            await self.bot.discordLogger.automod('kick', member,
                                                 f"Warn 4: `{reason if reason is not None else 'No reason given for warn'}`")
            try:
                await member.send(msg)
            except Forbidden:
                pass

            await member.kick(reason=f"Warn 4: `{reason}`")

        elif numOfWarns >= 5:
            msg += f"You have been banned from {ctx.guild.name} for getting {numOfWarns} warns."
            await self.bot.discordLogger.automod('ban', member,
                                                 f"Warn 5: `{reason if reason is not None else 'No reason given for warn'}`")
            try:
                await member.send(msg)
            except Forbidden:
                pass

            await member.ban(reason=f"Warn 5: `{reason}`")

        else:
            await member.send(msg)

    @checks.is_staff_or_perms("Mod", manage_roles=True, manage_channels=True)
    @commands.guild_only()
    @commands.command(aliases=["delwarn", 'unwarn'])
    async def deletewarn(self, ctx, member: discord.Member, warnNum: int):

        """Removes a single warn (Staff only)"""
        async with self.bot.db.acquire() as conn:
            userguildwarnsid = await conn.fetch("SELECT * FROM warns WHERE userid = $1 AND guildid = $2", member.id,
                                                ctx.guild.id)
            deletedwarn = None
            if userguildwarnsid:
                for num, record in enumerate(userguildwarnsid, 1):
                    if num == warnNum:
                        deletedwarn = DbWarns(record)
                        break

                if deletedwarn is None:
                    await ctx.send(f"This user does not have a warn {warnNum}")
                    return

                # just in case, should never trigger!
                if deletedwarn.guildid != ctx.guild.id:
                    await ctx.send("You cannot clear another guild's warns!")
                    return

                await conn.execute("DELETE FROM warns WHERE warnID = $1", deletedwarn.id)

            else:
                await ctx.send("This user has no warns on this server!")

            await ctx.send(f"Warn {warnNum} removed!")
            await self.bot.discordLogger.warnclear(ctx, 'clear', member, ctx.author, deletedwarn)

    @commands.guild_only()
    @commands.command()
    async def listwarns(self, ctx, member: typing.Union[discord.Member, int] = None):
        """
        List your own warns or someone else's warns.
        Only the staff can view someone else's warns
        """
        inserver = True
        if not member:
            member = ctx.message.author

        elif isinstance(member, int):
            member = await self.bot.fetch_user(member)
            inserver = False

        has_perms = await checks.nondeco_is_staff_or_perms(ctx, "Mod", manage_roles=True)

        if not has_perms and member != ctx.message.author:
            return await ctx.send(
                f"{ctx.message.author.mention} You don't have permission to list other member's warns!")

        async with self.bot.db.acquire() as conn:
            warnrecords = await conn.fetch("SELECT * FROM warns WHERE userid = $1 AND guildid = $2", member.id,
                                           ctx.guild.id)

        if len(warnrecords) == 0:
            embed = discord.Embed(title=f"Warns for {member.name}#{member.discriminator}", color=member.color)
            embed.description = "There are none!"
            return await ctx.send(embed=embed)

        userWarns = []
        for warn in warnrecords:
            userWarns.append(DbWarns(warn))

        embed = discord.Embed(color=member.color)
        embed.set_author(name=f"List of warns for {member.name}#{member.discriminator}:", icon_url=member.avatar_url)

        for num, warn in enumerate(userWarns, 1):
            issuer = self.bot.get_user(warn.authorid) if self.bot.get_user(
                warn.authorid) is not None else await self.bot.fetch_user(warn.authorid)

            embed.add_field(name=f"\n\n{num} : {warn.time_stamp}",
                            value=f"""{warn.reason if warn.reason is not None else 'No reason given for warn'}\n
            Warn ID: {warn.id}\nIssuer: {issuer.name}#{issuer.discriminator}""")

        if not inserver:
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
            numOfwarns = await conn.fetchval("SELECT COUNT(warnid) FROM warns WHERE userID = $1 AND guildID = $2",
                                             member.id, ctx.guild.id)
            if numOfwarns is None:
                await ctx.send("No warns found")

            else:
                await self.bot.discordLogger.warnclear(ctx,'clear', member, ctx.author)
                await conn.execute("DELETE FROM warns WHERE userID = $1 AND guildid = $2", member.id, ctx.guild.id)
                await ctx.send(f"{numOfwarns} warns cleared from {member.name}")


def setup(bot):
    bot.add_cog(Warn(bot))
