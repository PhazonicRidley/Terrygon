import re
import typing
import string
from fuzzywuzzy import fuzz
import discord
from discord.ext import commands
from utils import checks


def char_str_replace(dictionary: dict, input_string: str) -> str:
    """Replaces character in a dictionary"""
    for k, v in dictionary.items():
        input_string = input_string.replace(k, v)

    return input_string


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
    @checks.is_staff_or_perms("Mod", manage_messages=True)
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
    @checks.is_staff_or_perms("Mod", manage_messages=True)
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
    @checks.is_staff_or_perms("Mod", manage_messages=True)
    @word_filter.command(name="update")
    async def update_word(self, ctx, word, punishment):
        """Updates punishment for a word"""

        # validate punishment
        punishment = punishment.lower()
        word = word.lower()
        if punishment not in ['delete', 'warn', 'notify']:
            return await ctx.send("Invalid punishment given, valid options are `warn`, `delete`, or `notify`")

        await self.bot.db.execute("UPDATE filtered_words SET punishment = $1 WHERE word = $2 AND guild_id = $3",
                                  punishment, word, ctx.guild.id)
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
            try:
                dm_msg = f"You have popped the filter on {member.guild}. " + "Your message has been deleted"
                await member.send(dm_msg)
            except discord.Forbidden:
                pass

        elif punishment == "warn":
            await message.delete()
            await self.bot.db.execute("INSERT INTO warns (userid, authorid, guildid, reason) VALUES ($1, $2, $3, $4)",
                                      member.id, self.bot.user.id, member.guild.id, "Filter Pop")
            try:
                dm_msg = f"You have popped the filter on {member.guild}. " + "You have been warned because of this."
                await member.send(dm_msg)
            except discord.Forbidden:
                pass
            punishment_data = await self.bot.db.fetchval(
                "SELECT warn_punishments FROM guild_settings WHERE guildid = $1",
                message.guild.id)
            cog = self.bot.get_cog("Warn")
            if punishment_data and cog:
                highest_punishment_value = max(punishment_data.keys())
                warn_num = int(
                    await self.bot.db.fetchval("SELECT COUNT(warnID) FROM warns WHERE userid = $1 AND guildid = $2;",
                                               member.id,
                                               member.guild.id))
                if str(warn_num) in list(punishment_data.keys()):
                    await cog.punish(member, warn_num, punishment_data[str(warn_num)])

                elif warn_num > int(highest_punishment_value):
                    await cog.punish(member, warn_num, punishment_data[str(highest_punishment_value)])

            elif not cog:
                msg = ":bangbang: Unable to load the Warn cog please contact a bot maintainer."
                # TODO: log properly
                await self.bot.discord_logger.custom_log("modlogs", message.guild, msg)

    async def check_staff_filter(self, message: discord.Message) -> bool:
        """Checks for filter bypass for staff"""
        is_staff = await checks.nondeco_is_staff_or_perms(message, self.bot.db, "Mod", manage_message=True)
        bypass_on = await self.bot.db.fetchval("SELECT staff_filter FROM guild_settings WHERE guildid = $1",
                                               message.guild.id)
        return is_staff and bypass_on

    @commands.Cog.listener()
    async def on_message(self, message):
        """Checks messages"""
        if message.guild is None:
            return

        staff_bypass = await self.check_staff_filter(message)
        is_whitelist = await self.bot.db.fetchval(
            "SELECT channel_id FROM whitelisted_channels WHERE channel_id = $1 AND guild_id = $2", message.channel.id,
            message.guild.id)
        is_me = self.bot.user == message.author
        if is_me or staff_bypass or is_whitelist:
            return

        filtered_words = await self.bot.db.fetch("SELECT word, punishment FROM filtered_words WHERE guild_id = $1",
                                                 message.guild.id)
        if filtered_words is None:
            return
        matches = []
        msg = re.sub(r"[^0-9a-zA-Z ]", "", message.content)
        for word_tup in filtered_words:
            word = word_tup[0]
            if len(word) < 5:
                spaced_res = re.search(" ".join(word), msg, re.I)
                no_white_space = re.sub(r" ", "", msg)
                res = re.search(word_tup[0], no_white_space, re.I)
                if spaced_res:
                    w_start, w_end = spaced_res.span(0)
                    beginning_isolated = False
                    ending_isolated = False
                    if w_start == 0 and msg[w_start + 1] == " ":
                        beginning_isolated = True
                    elif msg[w_start + 1] == " " and msg[w_start - 1] == " ":
                        beginning_isolated = True

                    if w_end == len(msg):
                        ending_isolated = True
                    elif msg[w_end] == " " or len(msg) == w_end:
                        ending_isolated = True

                    if not beginning_isolated or not ending_isolated:
                        continue

                    char_span = msg[w_start: w_end]
                    ratio = fuzz.ratio(word, char_span)
                    partial_ratio = fuzz.partial_ratio(word, char_span)
                    if ratio >= 70 or partial_ratio >= 70:
                        matches.append((spaced_res, word_tup[1]))

                elif res:
                    matches.append((res, word_tup[1]))

            else:
                no_white_space = re.sub(r" ", "", msg)
                res = re.search(word_tup[0], no_white_space, re.I)
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

    @commands.guild_only()
    @checks.is_staff_or_perms("Owner", administrator=True)
    @commands.command(name="staffbypass")
    async def staff_filter_bypass(self, ctx):
        """Toggles the staff whitelist for the filter"""
        bypass_on = await self.bot.db.fetchval("SELECT staff_filter FROM guild_settings WHERE guildid = $1",
                                               ctx.guild.id)
        if bypass_on:
            await self.bot.db.execute("UPDATE guild_settings SET staff_filter = false WHERE guildid = $1", ctx.guild.id)
            await ctx.send("Staff can no longer bypass the filter.")
        else:
            await self.bot.db.execute("UPDATE guild_settings SET staff_filter = true WHERE guildid = $1", ctx.guild.id)
            await ctx.send("Staff can now bypass the filter.")

    # whitelisted channels funcs (add/remove)
    @commands.guild_only()
    @checks.is_staff_or_perms("Admin", manage_channels=True)
    @commands.group(name="channelwhitelist", invoke_without_command=True, aliases=['whitelist'])
    async def channel_whitelist(self, ctx):
        """Channel whitelist for filter"""
        await ctx.send_help(ctx.command)

    @commands.guild_only()
    @checks.is_staff_or_perms("Admin", manage_channels=True)
    @channel_whitelist.command(name="add")
    async def whitelist_add(self, ctx, channel: discord.TextChannel = None):
        """Adds a text channel to the whitelist"""
        if channel is None:
            channel = ctx.channel

        if await self.bot.db.fetchval(
                "SELECT channel_id FROM whitelisted_channels WHERE channel_id = $1 AND guild_id = $2", channel.id,
                ctx.guild.id) is not None:
            return await ctx.send(f"{channel.mention} is already whitelisted")

        await self.bot.db.execute("INSERT INTO whitelisted_channels (channel_id, guild_id) VALUES ($1, $2)", channel.id,
                                  ctx.guild.id)
        await ctx.send(f"{channel.mention} is now whitelisted")
        await self.bot.discord_logger.channel_whitelist("channelwhitelist", channel, ctx.author)

    @commands.guild_only()
    @checks.is_staff_or_perms("Admin", manage_channels=True)
    @channel_whitelist.command(name="delete", aliases=['remove', 'del'])
    async def whitelist_remove(self, ctx, channel: typing.Union[discord.TextChannel, int] = None):
        """Removes a channel from the whitelist"""
        if channel is None:
            channel = ctx.channel
        if isinstance(channel, int):
            channel_id = channel
            output = f"{channel_id} is not being whitelisted."
        else:
            channel_id = channel.id
            output = f"{channel.mention} is not being whitelisted."
        if not await self.bot.db.fetchval(
                "SELECT channel_id FROM whitelisted_channels WHERE channel_id = $1 AND guild_id = $2", channel_id,
                ctx.guild.id):
            return await ctx.send(f"{channel.mention} is not whitelisted.")

        await self.bot.db.execute("DELETE FROM whitelisted_channels WHERE channel_id = $1 AND guild_id = $2",
                                  channel_id, ctx.guild.id)
        await ctx.send(output)
        await self.bot.discord_logger.channel_whitelist("channeldewhitelist", channel, ctx.author)

    @commands.guild_only()
    @checks.is_staff_or_perms("Mod", manage_channels=True)
    @channel_whitelist.command(name="list")
    async def whitelist_list(self, ctx):
        """Lists whitelisted channels"""
        channels = ""
        deleted_channels = ""
        c_ids = await self.bot.db.fetchrow("SELECT channel_id FROM whitelisted_channels WHERE guild_id = $1",
                                           ctx.guild.id)
        for c_id in c_ids:
            c = ctx.guild.get_channel(c_id)
            if not c:
                deleted_channels += f"- {c_id}\n"
            else:
                channels += f"- {c.mention}"

        embed = discord.Embed(title=f"List of whitelisted channels")
        embed.description = channels
        if deleted_channels:
            embed.add_field(name=":warning: Deleted channels, please remove with the delete command!",
                            value=deleted_channels)

        try:
            await ctx.author.send(embed=embed)
            await ctx.message.add_reaction("\U0001f4ec")
        except discord.Forbidden:
            pass


def setup(bot):
    bot.add_cog(Filter(bot))
