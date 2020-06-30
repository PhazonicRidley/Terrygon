import discord
from discord.ext import commands
from utils import checks, common
import webcolors
import typing


class Trusted(commands.Cog):

    def __init__(self, bot):
        self.bot = bot


    async def getTrustedList(self, guildid) -> list:
        """Returns a list of trusted user ids for a guild, or None if none are found"""
        return await self.bot.db.fetchval("SELECT trusteduid FROM trustedusers WHERE guildid = $1", guildid)
    
    @commands.guild_only()
    @commands.command()
    async def listtrusted(self, ctx):
        """Lists a guild's trusted users"""

        trustedids = await self.getTrustedList(ctx.guild.id)
        embed = discord.Embed(title=f"Trusted users for {ctx.guild.name}", colour=common.gen_color(ctx.guild.id))
        
        if not trustedids:
            embed.description = "No trusted users!"
            return await ctx.send(embed=embed)

        deletedusers = False
        deletedusers = ""
        trusteduserstr = ""
        for uid in trustedids:
            user = self.bot.get_user(uid) if self.bot.get_user(uid) else await self.bot.fetch_user(uid)
            if user is None:
                deletedusers = True
                deletedusers += f"- \U000026a0 {uid}\n"
            else:
                trusteduserstr += f"- {user}\n"

        embed.description = trusteduserstr
        if deletedusers:
            embed.add_field(name="**Deleted user IDs!**", value=deletedusers + "\nPlease delete these users from the database!")
        await ctx.send(embed=embed)

    @commands.guild_only()
    @checks.is_staff_or_perms("Admin", manage_server=True)
    @commands.command()
    async def trust(self, ctx, member: discord.Member):
        """Adds a member to the guild's trusted list (Admin+ or manage server)"""
        trustedlist = await self.getTrustedList(ctx.guild.id)
        if trustedlist is None or member.id not in trustedlist:
            await self.bot.db.execute("UPDATE trustedusers SET trusteduid = array_append(trusteduid, $1) WHERE guildid = $2", member.id, ctx.guild.id)
            await ctx.send(f"Added {member} to {ctx.guild.name}'s trusted list!")
        else:
            await ctx.send("This user is already trusted!")

    @commands.guild_only()
    @checks.is_staff_or_perms("Admin", manage_server=True)
    @commands.command()
    async def untrust(self, ctx, member: typing.Union[discord.Member, int]):
        """Removes a member to the guild's trusted list (Admin+ or manage server)"""
        trustedlist = await self.getTrustedList(ctx.guild.id)
        if isinstance(member, discord.Member):
            member = member.id
        
        if trustedlist is None or len(trustedlist) == 0:
            return await ctx.send("No trusted users saved")

        elif member in trustedlist:
            await self.bot.db.execute("UPDATE trustedusers SET trusteduid = array_remove(trusteduid, $1) WHERE guildid = $2", member, ctx.guild.id)
            await ctx.send("User removed from trusted list!")
        else:
            await ctx.send("This user is not trusted")


    @checks.is_trusted_or_perms(manage_messages=True)
    @commands.command()
    async def pin(self, ctx, message: discord.Message):
        """Pins a message (Trusted+)"""
        if message.pinned:
            return await ctx.send("Message has already been pinned")

        try:
            await message.pin()
        except discord.Forbidden:
            return await ctx.send("I do not have permission to pin messages!")
        
        await self.bot.discordLogger.messagepinned('pin', ctx.author, message)
            
    @checks.is_trusted_or_perms(manage_messages=True)
    @commands.command()
    async def unpin(self, ctx, message: discord.Message):
        """Unpins a message (Trusted+)"""
        if not message.pinned:
            return await ctx.send("Message is not pinned")
        
        try:
            await message.unpin()
        except discord.Forbidden:
            return await ctx.send("I do not have permission to unpin messages")
        
        await ctx.send("Message unpinned")
        await self.bot.discordLogger.messagepinned('unpin', ctx.author, message)

def setup(bot):
    bot.add_cog(Trusted(bot))
