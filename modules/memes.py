import random
import math
import discord
from discord.ext import commands
from utils import checks, common, paginator


class Memes(commands.Cog):
    """Meme Cog"""

    def __init__(self, bot):
        self.bot = bot

    @commands.guild_only()
    @commands.group(name="meme", aliases=['m'], invoke_without_command=True)
    async def memes(self, ctx: commands.Context, meme_name: str = None):
        """Shows a meme command."""
        if not meme_name:
            return await self.list_memes(ctx)
        meme_name = meme_name.lower()
        meme = await self.bot.db.fetchval(
            "SELECT content FROM memes WHERE (guild_id = $1 OR guild_id = 0) AND name = $2", ctx.guild.id, meme_name)
        if not meme:
            await ctx.send(f"No meme `{meme_name}` found.")
        else:
            await ctx.send(meme)

    @commands.guild_only()
    @checks.is_trusted_or_perms(manage_messages=True)
    @memes.command(name="add")
    async def add_meme(self, ctx: commands.Context, meme_name: str, *, meme_content: str):
        """Adds a server meme."""
        meme_name = meme_name.lower()
        if meme_name in ('add', 'remove', 'list', 'del', 'delete'):
            return await ctx.send("Cannot use this name for a meme, this a command name.")

        exists = await self.bot.db.fetchval("SELECT name FROM memes WHERE guild_id = $1 AND name = $2", ctx.guild.id,
                                            meme_name)
        if exists:
            res, msg = await paginator.YesNoMenu("Meme exists, would you like to update it?").prompt(ctx)
            if res:
                await self.bot.db.execute("UPDATE memes SET content = $1 WHERE guild_id = $2 AND name = $3", meme_content,
                                          ctx.guild.id, meme_name)
                await msg.edit(content=f"Updated meme `{meme_name}`.")
            else:
                await msg.edit(content="Did not update meme.")
        else:
            await self.bot.db.execute("INSERT INTO memes (guild_id, name, content) VALUES ($1, $2, $3)", ctx.guild.id,
                                      meme_name, meme_content)
            await ctx.send(f"Added meme `{meme_name}`.")

    @commands.guild_only()
    @checks.is_trusted_or_perms(manage_messages=True)
    @memes.command(name="remove", aliases=['del', 'delete'])
    async def remove_meme(self, ctx: commands.Context, meme_name):
        """Removes a server meme"""
        meme_name = meme_name.lower()
        exists = await self.bot.db.fetchval("SELECT name FROM memes WHERE guild_id = $1 AND name = $2", ctx.guild.id,
                                            meme_name)
        if exists:
            await self.bot.db.execute("DELETE FROM memes WHERE name = $1 AND guild_id = $2", meme_name, ctx.guild.id)
            await ctx.send(f"Meme `{meme_name}` deleted.")
        else:
            await ctx.send("Meme does not exist.")

    async def list_memes(self, ctx: commands.Context):
        """Lists a server's memes."""
        guild_memes = await self.bot.db.fetch("SELECT name FROM memes WHERE guild_id = $1", ctx.guild.id)
        if not guild_memes:
            return await ctx.send(f"No memes saved for {ctx.guild.name}")
        guild_memes = [f"- `{m['name']}`\n" for m in guild_memes]
        embed = discord.Embed(title=f"Memes for {ctx.guild.name}", color=common.gen_color(ctx.guild.id))
        pages = paginator.ReactDeletePages(paginator.BasicEmbedMenu(guild_memes, per_page=10, embed=embed),
                                           clear_reactions_after=True, check_embeds=True)
        await pages.start(ctx)

    @commands.guild_only()
    @memes.command(name="list")
    async def list_guild_memes(self, ctx: commands.Context):
        """Lists a server's memes."""
        await self.list_memes(ctx)

    @commands.command()
    async def bean(self, ctx, member: discord.Member = None):
        """Beans a member."""
        if member is None:
            member = ctx.author
        # this is hard coded lol
        await ctx.send(
            f"I've beaned {member}. <a:abeanhammer:511352809245900810>")  # yes i know its hardcoded, ill fix at a later time.

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

        await ctx.send(f"{member} is now mooted!")

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
        celsius = random.randint(38, 100)
        if member is None:
            member = ctx.author

        await ctx.send(
            f"🔥 I've warmed {member}. User is now {celsius}°C ({common.convert_c_to_f(celsius)}°F) ({celsius + 273}K)")

    @commands.command(aliases=['cool'])
    async def chill(self, ctx, member: discord.Member = None):
        """
        Brrr, c-c-Chilly!
        """
        celsius = random.randint(-273, 34)
        if member is None:
            member = ctx.author

        await ctx.send(
            f"🧊 I've chilled {member}. User is now {celsius}°C ({common.convert_c_to_f(celsius)}°F) ({celsius + 273}K)")


async def setup(bot):
    await bot.add_cog(Memes(bot))
