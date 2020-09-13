# meems
import discord
from discord.ext import commands
from logzero import setup_logger
from utils import checks
from discord.utils import escape_mentions
from utils import paginator

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
    @commands.command(aliases=['m', 'M'])
    async def meme(self, ctx, meme_name: str):
        """Posts a saved meme, guild memes have priority"""
        async with self.bot.db.acquire() as conn:
            if not await conn.fetchval("SELECT guildmemes->$1 FROM memes WHERE guildid = $2", meme_name,
                                       ctx.guild.id) and not await conn.fetchval(
                    "SELECT guildmemes->$1 FROM memes WHERE guildid = 0", meme_name):
                return await ctx.send("Meme not found in database for this server or globally!")

            meme = await conn.fetchval("SELECT guildmemes->>$1 FROM memes WHERE guildid = $2", meme_name, ctx.guild.id)
            if not meme:
                meme = await conn.fetchval("SELECT guildmemes->>$1 FROM memes WHERE guildid = 0", meme_name)

            return await ctx.send(meme)

    @checks.is_trusted_or_perms(manage_messages=True)
    @commands.command()
    async def addmeme(self, ctx, name, *, meme_content):
        """Adds a guild meme to the bot (Trusted+ only)"""

        await self.setup_db_guild(ctx.guild.id)
        await self.add_meme_db(escape_mentions(name), escape_mentions(meme_content), ctx.guild.id)
        await ctx.send("Added meme")

    @checks.is_trusted_or_perms(manage_messages=True)
    @commands.command()
    async def delmeme(self, ctx, meme_name: str):
        """Removes a guild meme from the bot (Trusted+ only)"""
        await self.setup_db_guild(ctx.guild.id)
        await ctx.send(await self.del_meme_db(meme_name, ctx.guild.id))

    @commands.command()
    async def listmemes(self, ctx):
        """Lists a guild's memes as well as the bot's global memes"""
        await self.setup_db_guild(ctx.guild.id)
        guild_memes = (await self.bot.db.fetchval("SELECT guildmemes FROM memes WHERE guildid = $1", ctx.guild.id))
        global_memes = (await self.bot.db.fetchval("SELECT guildmemes FROM memes WHERE guildid = 0"))
        embed = discord.Embed(title=f"Memes for {ctx.guild.name}", color=0xe55715)
        guild_memes_list = []
        global_meme_string = ""
        if guild_memes:
            for meme in guild_memes.keys():
                guild_memes_list.append(str(meme))
        else:
            guild_memes_list.append("**No guild memes saved**")
        guild_memes_list.sort()
        if global_memes:
            global_memes.sort()
            for meme in global_memes.keys():
                global_meme_string += f"{meme}\n"
        else:
            global_meme_string = "No global memes found!"

        embed.description = "**Guild Memes**"
        embed.add_field(name="**Global Memes**", value=global_meme_string, inline=False)

        pages = paginator.ReactDeletePages(paginator.BasicEmbedMenu(guild_memes_list, per_page=8, embed=embed),
                                           clear_reactions_after=True, check_embeds=True)
        await pages.start(ctx)

    @checks.is_bot_owner()
    @commands.command()
    async def addglobalmeme(self, ctx, name, *, meme_content):
        """Adds a global meme to the bot that can be used anywhere (Bot owner's only)"""
        await self.setup_db_guild(0)
        await self.add_meme_db(escape_mentions(name), escape_mentions(meme_content), 0)
        await ctx.send("Added global meme")

    @checks.is_bot_owner()
    @commands.command()
    async def delglobalmeme(self, ctx, meme_name: str):
        """Removes a global meme"""
        await ctx.send(await self.del_meme_db(meme_name, 0))

    @commands.command()
    async def bean(self, ctx, member: discord.Member = None):
        """Beans a member."""
        if member is None:
            member = ctx.author
        # this is hard coded lol
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

    async def del_meme_db(self, name: str, guild_id: int):
        """Remove a meme from the database"""
        async with self.bot.db.acquire() as conn:
            if not await conn.fetchval("SELECT guildmemes->>$1 FROM memes WHERE guildid = $2", name, guild_id):
                return "This meme does not exist!"

            await conn.execute("""UPDATE memes SET guildmemes = guildmemes::jsonb - $1::TEXT WHERE guildid = $2""",
                               name, guild_id)
            return "Meme deleted"

    async def add_meme_db(self, name: str, meme_content: str, guild_id: int):
        """Adds a meme to the database"""
        async with self.bot.db.acquire() as conn:
            if not await conn.fetchval("SELECT guildmemes FROM memes WHERE guildid = $1", guild_id):
                await conn.execute("""UPDATE memes SET guildmemes = 
                jsonb_build_object($1::TEXT, $2::TEXT)::jsonb
                WHERE guildid = $3""", name, meme_content, guild_id)
            else:
                await conn.execute("""
                UPDATE memes SET guildmemes = guildmemes::jsonb || 
                jsonb_build_object($1::TEXT, $2::TEXT)::jsonb
                WHERE guildid = $3""", name, meme_content, guild_id)

    async def setup_db_guild(self, guild_id):
        """Adds a json config for a guild to store memes in"""
        async with self.bot.db.acquire() as conn:
            if await conn.fetchval("SELECT guildid FROM memes WHERE guildid = $1", guild_id) is None:
                await conn.execute("INSERT INTO memes (guildid) VALUES ($1)", guild_id)

    async def get_memes_from_db(self, guild_id: int):
        """Gets a guild's saved memes"""
        async with self.bot.db.acquire() as conn:
            guild_memes = await conn.fetch("SELECT guildmemes FROM memes WHERE guildid = $1", guild_id)
            global_memes = await conn.fetch("SELECT guildmemes FROM memes WHERE guildid = 0")
            return guild_memes + global_memes


def setup(bot):
    bot.add_cog(Memes(bot))
