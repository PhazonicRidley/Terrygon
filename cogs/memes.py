# meems
# TODO write up docs on how to run this standalone
import discord
from discord.ext import commands
from logzero import setup_logger
from utils import checks
from discord.utils import escape_mentions
# set up console logging
memecogconsolelog = setup_logger(name='memecogconsolelog', logfile='logs/memes.log', maxBytes=1000000)

# might change later, should be instructed on how to configure for standalone
# "guildid" 0 represents global, all memes put in there are global and are accessible by any server
cogSchema = """
CREATE TABLE IF NOT EXISTS memes (
        guildid BIGINT PRIMARY KEY,
        guildmemes jsonb
    );
"""


class Memes(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    @commands.guild_only()
    @commands.command()
    async def meme(self, ctx, memeName: str, globforce: str = None):
        """Posts a meme post global as your final arg if you want to force a global meme, guild memes take priority"""
        async with self.bot.db.acquire() as conn:
            if not await conn.fetchval("SELECT guildmemes->$1 FROM memes WHERE guildid = $2", memeName, ctx.guild.id) and not await conn.fetchval("SELECT guildmemes->$1 FROM memes WHERE guildid = 0", memeName):
                return await ctx.send("Meme not found in database for this server or globally!")

            meme = await conn.fetchval("SELECT guildmemes->>$1 FROM memes WHERE guildid = $2", memeName, ctx.guild.id)
            if not meme or globforce:
                meme = await conn.fetchval("SELECT guildmemes->>$1 FROM memes WHERE guildid = 0", memeName)

            return await ctx.send(meme)

    @checks.is_trusted_or_perms(manage_messages=True)
    @commands.command()
    async def addmeme(self, ctx, name, *, memeContent):
        """Adds a guild meme to the bot (Trusted+ only)"""

        await self.setupdbguild(ctx.guild.id)
        await self.addmemedb(escape_mentions(name), escape_mentions(memeContent), ctx.guild.id)
        await ctx.send("Added meme")

    @checks.is_trusted_or_perms(manage_messages=True)
    @commands.command()
    async def delmeme(self, ctx, memename: str):
        """Removes a guild meme from the bot (Trusted+ only)"""
        await self.setupdbguild(ctx.guild.id)
        await ctx.send(await self.delmemedb(memename, ctx.guild.id))

    @commands.command()
    async def listmemes(self, ctx):
        await self.setupdbguild(ctx.guild.id)
        guildmemes = (await self.bot.db.fetchval("SELECT guildmemes FROM memes WHERE guildid = $1", ctx.guild.id))
        globalmemes = (await self.bot.db.fetchval("SELECT guildmemes FROM memes WHERE guildid = 0"))
        embed = discord.Embed(title=f"Memes for {ctx.guild.name}", color=0xe55715)
        guildmemestring = ""
        globalmemestring = ""
        if guildmemes:
            for meme in guildmemes.keys():
                guildmemestring += f"{meme}\n"
        else:
            guildmemestring = "No memes found!"

        if globalmemes:
            for meme in globalmemes.keys():
                globalmemestring += f"{meme}\n"
        else:
            globalmemestring = "No global memes found!"

        embed.add_field(name="**Guild Memes**", value=guildmemestring, inline=True)
        embed.add_field(name="**Global Memes**", value=globalmemestring, inline=True)
        await ctx.send(embed=embed)

    @checks.is_bot_owner()
    @commands.command()
    async def addglobalmeme(self, ctx, name, *, memeContent):
        """Adds a global meme to the bot that can be used anywhere (Bot owner's only)"""
        await self.setupdbguild(0)
        await self.addmemedb(escape_mentions(name), escape_mentions(memeContent), 0)
        await ctx.send("Added global meme")

    @checks.is_bot_owner()
    @commands.command()
    async def delglobalmeme(self, ctx, memename: str):
        """Removes a global meme"""
        #await self.setupdbguild(0)
        await ctx.send(await self.delmemedb(memename, 0))

        # move to memes eventuallyTM
    @commands.command()
    async def bean(self, ctx, member: discord.Member = None):
        """Beans a member."""
        if member is None:
            member = ctx.author

        await ctx.send(f"I've beaned {member}. <a:abeanhammer:511352809245900810>")

    @commands.command()
    async def kicc(self, ctx, member: discord.Member = None):
        """Moots a user. """
        if member is None:
            member = ctx.author

        await ctx.send(f"I've kicced {member}")

    @commands.command()
    async def moot(self, ctx, member: discord.Member = None):
        """Moots a user. """
        if member is None:
            member = ctx.author

        await ctx.send(f"{member} can no longer speak!")

    @commands.command()
    async def unmoot(self, ctx, member: discord.Member = None):
        """unmoots a user."""
        if member is None:
            member = ctx.author

        await ctx.send(f"{member} is no longer mooted!")

    @commands.command()
    async def warm(self, ctx, member: discord.Member = None):
        """
        Woah, toasty!
        """
        if member is None:
            member = ctx.author

        await ctx.send(f"🚩 I've warmed {member}.")
    # util functions
    # saving this just in case, it works, just not being used so commented
    """async def isimagevideo(self, url):
        "detects file type of an image from the internet"
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url) as resp:

                    if re.match("image/+", resp.headers.get('content-type')):
                        return 'img'

                    elif re.match('video/+', resp.headers.get('content-type')):
                        return 'vid'
                    else:
                        return None
            except aiohttp.InvalidURL:
                return None"""

    async def delmemedb(self, name: str, guildid: int):
        """Remove a meme from the database"""
        async with self.bot.db.acquire() as conn:
            if not await conn.fetchval("SELECT guildmemes->>$1 FROM memes WHERE guildid = $2", name, guildid):
                return "This meme does not exist!"

            await conn.execute("""UPDATE memes SET guildmemes = guildmemes::jsonb - $1::TEXT WHERE guildid = $2""",
                               name, guildid)
            return "Meme deleted"

    async def addmemedb(self, name: str, memecontent: str, guildid: int):
        """Adds a meme to the database"""
        async with self.bot.db.acquire() as conn:
            if not await conn.fetchval("SELECT guildmemes FROM memes WHERE guildid = $1", guildid):
                await conn.execute("""UPDATE memes SET guildmemes = 
                jsonb_build_object($1::TEXT, $2::TEXT)::jsonb
                WHERE guildid = $3""", name, memecontent, guildid)
            else:
                await conn.execute("""
                UPDATE memes SET guildmemes = guildmemes::jsonb || 
                jsonb_build_object($1::TEXT, $2::TEXT)::jsonb
                WHERE guildid = $3""", name, memecontent, guildid)

    async def setupdbguild(self, guildid):
        """Adds a json config for a guild to store memes in"""
        async with self.bot.db.acquire() as conn:
            if await conn.fetchval("SELECT guildid FROM memes WHERE guildid = $1", guildid) is None:
                await conn.execute("INSERT INTO memes (guildid) VALUES ($1)", guildid)



    async def getmemesfromdb(self, guildid: int):
        """Gets a guild's saved memes"""
        async with self.bot.db.acquire() as conn:
            guildmemes = await conn.fetch("SELECT guildmemes FROM memes WHERE guildid = $1", guildid)
            globalmemes = await conn.fetch("SELECT guildmemes FROM memes WHERE guildid = 0")
            return guildmemes + globalmemes


def setup(bot):
    bot.add_cog(Memes(bot))
