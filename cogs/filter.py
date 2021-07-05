import re

import discord
from discord.ext import commands
from utils import checks


class Filter(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    async def word_in_filter(self, word, guild):
        """Checks if a word is in the filter for a guild"""
        return await self.bot.db.fetchval("SELECT id FROM filtered_words WHERE guild_id = $1 AND word = $2", guild.id,
                                          word)

    # filter words funcs (add/remove)
    @commands.guild_only()
    @commands.group(name="wordfilter", invoke_without_command=True)
    async def word_filter(self, ctx):
        """Adds or removes words from the filter"""
        await ctx.send_help(ctx.command)

    @commands.guild_only()
    @word_filter.command(name="add")
    async def add_word(self, ctx, word, punishment):
        """Adds a word to the filter.
        -word: the word you want to add to the filter.
        - punishment: either `delete` for message deletion, `warn` for message deletion and a warning, `notify` just to log that a user said the word.
        """
        # validate punishment
        punishment = punishment.lower()
        word = word.replace(" ", "").lower()
        if punishment not in ['delete', 'warn', 'notify']:
            return await ctx.send("Invalid punishment given, valid options are `warn`, `delete`, or `notify`")

        # check if word is in list
        if await self.word_in_filter(word, ctx.guild):
            return await ctx.send("Word is already in filter (filter ignores case)")

        await self.bot.db.execute("INSERT INTO filtered_words (word, guild_id, punishment) VALUES ($1, $2, $3)", word,
                                  ctx.guild.id, punishment)
        await ctx.send("Word added to the filter")
        await self.bot.discord_logger.word_filter_update("wordadd", word, ctx.author, punishment)

    @commands.guild_only()
    @word_filter.command(name="delete", aliases=["remove", "del"])
    async def del_word(self, ctx, word):
        """Removes a word from the filter"""
        word = word.lower()
        w_id = await self.word_in_filter(word, ctx.guild)
        if not w_id:
            return await ctx.send("Word is not in filter")

        await self.bot.db.execute("DELETE FROM filtered_words WHERE id = $1", w_id)
        await ctx.send("Word removed from filter")
        await self.bot.discord_logger.word_filter_update("worddelete", word, ctx.author)

    @commands.guild_only()
    @word_filter.command(name="update")
    async def update_word(self, ctx, word, punishment):
        """Updates punishment for a word"""

        # validate punishment
        punishment = punishment.lower()
        word = word.lower()
        if punishment not in ['delete', 'warn', 'notify']:
            return await ctx.send("Invalid punishment given, valid options are `warn`, `delete`, or `notify`")

        await self.bot.db.execute("UPDATE filtered_words SET punishment = $1 WHERE word = $2 AND guild_id = $3",
                                  punishment, word, ctx.guid.id)
        await ctx.send("Word punishment updated.")
        await self.bot.discord_logger.word_filter_update("wordupdate", word, ctx.author, punishment)

    @commands.guild_only()
    @word_filter.command(name="list")
    async def list_words(self, ctx):
        """Lists filtered words"""
        filtered_words = await self.bot.db.fetch("SELECT word, punishment FROM filtered_words WHERE guild_id = $1",
                                                 ctx.guild.id)
        embed = discord.Embed(title=f"Filtered words for {ctx.guild}", color=discord.Color.orange())
        word_string = ""
        for w, p in filtered_words:
            word_string += f"- `{w}` Punishment: {p.title()}\n"

        embed.description = word_string
        await ctx.author.send(embed=embed)
        try:
            await ctx.message.add_reaction("\U0001f4ec")
        except discord.Forbidden:
            pass

    async def punish(self, member, message, punishment):
        """Logs and gives punishment"""
        if punishment == "delete":
            await message.delete()
            dm_tag = "Your message has been deleted"

        elif punishment == "warn":
            await message.delete()
            await self.bot.db.execute("INSERT INTO warns (userid, authorid, guildid, reason) VALUES ($1, $2, $3, $4)",
                                      member.id, self.bot.user.id, member.guild.id, "Filter Pop")
            dm_tag = "You have been warned because of this."
        else:
            return

        try:
            dm_msg = f"You have popped the filter on {member.guild} " + dm_tag
            await member.send(dm_msg)
        except discord.Forbidden:
            pass

    @commands.Cog.listener()
    async def on_message(self, message):
        """Checks messages"""
        if self.bot.user == message.author:
            return
        filtered_words = await self.bot.db.fetch("SELECT word, punishment FROM filtered_words WHERE guild_id = $1",
                                                 message.guild.id)
        if filtered_words is None:
            return
        matches = []
        no_whitespace_message = message.content.replace(" ", "")
        no_whitespace_message = re.sub(r"[^0-9a-zA-Z]+", "", no_whitespace_message)
        for word_tup in filtered_words:
            res = re.search(word_tup[0], no_whitespace_message, re.I)
            if res:
                matches.append((res, word_tup[1]))

        if len(matches) == 0:
            return

        # highlight filtered words (thanks kurisu)
        highlighted_message = message.content
        for match_tuple in matches:
            match = match_tuple[0]
            w_start, w_end = match.span(0)
            highlighted_message = f"{highlighted_message[:w_start]}**{match.group(0)}**{highlighted_message[w_end:]}"

        if next((i for i, v in enumerate(matches) if v[1] == 'warn'), None) is not None:
            await self.punish(message.author, message, 'warn')
            highest_punishment = 'warn'
        elif next((i for i, v in enumerate(matches) if v[1] == 'delete'), None) is not None:
            await self.punish(message.author, message, 'delete')
            highest_punishment = 'delete'
        else:
            highest_punishment = 'notify'

        # log
        await self.bot.discord_logger.filter_pop(message.author, highlighted_message, highest_punishment)

    # whitelisted channels funcs (add/remove)
    # filter function (TESTING WITH REGEX TO START)
    # - staff is always whitelisted
    # - ignore whitelisted channels

    # punishments on filter breaks
    # - warns
    # - deletes
    # - notifications


def setup(bot):
    bot.add_cog(Filter(bot))