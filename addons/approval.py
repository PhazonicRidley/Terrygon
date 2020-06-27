from discord import Member, errors
from discord.errors import Forbidden
from discord.ext import commands
from utils import checks, errors
import asyncpg


class Approval(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    @checks.is_staff_or_perms("Owner", administrator=True)
    @commands.guild_only()
    @commands.command()
    async def toggleapproval(self, ctx):
        """Enables or disables a server's approval system (Owners only)"""

        async with self.bot.db.acquire() as conn:
            if await conn.fetchval("SELECT approvedRole FROM roles WHERE guildID = $1", ctx.guild.id) is None:
                await ctx.send("Approval role not set in database, please set that first!")
                return

            status = await conn.fetchval("SELECT approvalSystem FROM guild_settings WHERE guildID = $1", ctx.guild.id)
            if status:
                await conn.execute("UPDATE guild_settings SET approvalSystem = FALSE WHERE guildID = $1", ctx.guild.id)
                await self.bot.discordLogger.togglelogsetup('unset', 'approval system', ctx.author, 'modlogs')
                await ctx.send("Approval system disabled")

            else:
                await conn.execute("UPDATE guild_settings SET approvalSystem = TRUE WHERE guildID = $1", ctx.guild.id)
                await self.bot.discordLogger.togglelogsetup('unset', 'approval system', ctx.author, 'modlogs')
                await ctx.send("Approval system enabled! use .approve to let new members in")

    @checks.is_staff_or_perms("Mod", manage_roles=True)
    @commands.guild_only()
    @commands.command()
    async def approve(self, ctx, member: Member):
        """Approve members"""

        async with self.bot.db.acquire() as conn:
            if not (await conn.fetchrow("SELECT approvalSystem FROM guild_settings WHERE guildID = $1", ctx.guild.id))[0]:
                await ctx.send("Approval system disabled, you have no need for this!")
                return

            approved_role = ctx.guild.get_role(
                await conn.fetchval("SELECT approvedRole FROM roles WHERE guildID = $1", ctx.guild.id))
            if approved_role in member.roles or await conn.fetchval(
                    "SELECT userID FROM approvedMembers WHERE guildID = $1", ctx.guild.id) == member.id:
                await ctx.send("Member already approved")
                return

            try:
                await member.add_roles(approved_role)
                await ctx.send(f"{self.bot.discordLogger.emotes['approve']} {member} has been approved!")
                await self.bot.discordLogger.modlogs(ctx, 'approve', member, ctx.author)
            except Forbidden:
                return await ctx.send("Cannot add roles, please check my permissions")

            await conn.execute("INSERT INTO approvedMembers (userID, guildID) VALUES ($1, $2)", member.id, ctx.guild.id)

            try:
                await member.send(
                    f"You have been approved on {ctx.guild.name} welcome, please read the rules of the server!")
            except Forbidden:
                pass

    @checks.is_staff_or_perms("Mod", manage_roles=True)
    @commands.guild_only()
    @commands.command()
    async def unapprove(self, ctx, member: Member):
        """Unapprove members"""

        async with self.bot.db.acquire() as conn:
            if not (await conn.fetchrow("SELECT approvalSystem FROM guild_settings WHERE guildID = $1", ctx.guild.id))[0]:
                await ctx.send("Approval system disabled, you have no need for this!")
                return

            approved_role = ctx.guild.get_role(
                await conn.fetchval("SELECT approvedRole FROM roles WHERE guildID = $1", ctx.guild.id))
            if not approved_role in member.roles or not await conn.fetchval(
                    "SELECT userID FROM approvedMembers WHERE guildID = $1", ctx.guild.id):
                await ctx.send("Member not approved")
                return

            try:
                await member.remove_roles(approved_role)
                await ctx.send(f"{self.bot.discordLogger.emotes['unapprove']} {member} has been unapproved")
                await self.bot.discordLogger.modlogs(ctx, 'unapprove', member, ctx.author)
            except Forbidden:
                await ctx.send("Unable to remove roles, please check my permissions")
                return

            await conn.execute("DELETE FROM approvedMembers WHERE userID = $1 AND guildID = $2", member.id,
                               ctx.guild.id)


def setup(bot):
    bot.add_cog(Approval(bot))
