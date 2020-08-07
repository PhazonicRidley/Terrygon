from datetime import date, datetime
import discord
from discord.utils import escape_mentions
from utils import errors
from discord.channel import TextChannel
import typing
import logzero
from logzero import logger as consoleLogger
from utils import checks
from discord.utils import escape_mentions

logzero.logfile("logs/discordLogerrors.log", maxBytes=1e6)


class Logger():

    def __init__(self, bot):
        self.bot = bot
        # temp emoji dict for logging, will convert to full sql database json thingy later
        self.emotes = {
            # mod actions
            'ban': "\U000026d4",
            'kick': "\U0001f462",
            'mute': "\U0001f507",
            'unmute': "\U0001f509",
            'warn': "\U000026a0",
            'approve': "\U0001f44d",
            "unapprove": "\U0001f44e",
            "lock": ":lock:",
            "unlock": "\U0001f513",
            "clear": "\U0001f5d1",
            "slowmode": "\U0001f551",
            # utils
            "success": "\U00002705",
            "failure": "\U0001f4a2",
            "reason": "\U0000270f",
            "id": "\U0001f3f7",
            "creationdate": "\U0001f5d3",
            # member altering
            "join": "\U0001f44b",
            "left": ":arrow_left:",
            "username": "\U0001f5d2",
            "discriminator": "\U0001f522",
            "nickname": "\U0001f50e",
            "add role": "\U0001f6e1",
            "remove role": "\U0000274c",
            # message actions
            "msgedit": "\U0001f4dd",
            "mdelete": "\U0000274c",
            "message": "\U0001f5d2",  # util emote for messaging logs
            # audit logs
            "creation": "\U00002795",
            "update": "\U000023eb",
            "deletion": "\U00002796",
            "movemembervc": "\U00002195",
            "vcmute": "\U0001f507",
            "vcdisconnect": "\U0000274c",
            "addbot": "\U0001f916",
            "unban": "\U00002b55",
            "pin": "\U0001f4cc",
            "unpin": "\U0001f6ab",
            # misc
            "boterror": "",
            "info": "\U00002139",
            "unset": "",
            "set": "",
            "shutdown": "",
            "restart": "",
            "notice": "\U00002139"
        }

    async def dispatch(self, dbChan, guild: discord.Guild, logtype, msg, embed: discord.Embed = None):
        # make the right query
        if not dbChan in ("modlogs", "memberlogs", "messagelogs", "auditlogs"):
            raise errors.loggingError(logtype, dbChan)

        query = f"SELECT {dbChan} FROM log_channels WHERE guildID = $1"
        async with self.bot.db.acquire() as conn:

            channelid = await conn.fetchval(query, guild.id)
            if channelid is None:
                # consoleLogger.warning(f"{logtype} log failed! in {guild.name}, could not find {dbChan} log channel in database for this guild.\
                # probably no configuration for {dbChan} logs!")
                raise errors.loggingError(logtype, guild)

            else:
                logchannel = self.bot.get_channel(channelid)
                if logchannel is None:
                    consoleLogger.error("Did not parse asyncpg record object properly.")
                else:
                    await logchannel.send(msg)
                    if embed:
                        await logchannel.send(embed=embed)

    async def modlogs(self, ctx, logtype: str, target: typing.Union[discord.Member, discord.TextChannel, discord.Role],
                      author: discord.Member, reason=None, **kwargs) -> str:
        """Logs bans, kicks, mutes, unmutes, warns, and other moderation actions in the mod logs channel"""
        if reason is not None:
            reason = escape_mentions(reason)

        if logtype == 'ban' or logtype == 'softban':
            msg = f"{self.emotes['ban']} **__User {logtype.title()}ned:__** {author.mention} | {author.name}#{author.discriminator} {logtype}ned {target.mention} | {target.name}#{target.discriminator}\n{self.emotes['id']} User ID: {target.id}"
            if reason is not None:
                msg += f"\n{self.emotes['reason']}Reason: {reason}"

        elif (
                logtype == 'mute' or logtype == 'unmute' or logtype == 'approve' or logtype == 'unapprove') and isinstance(
            target, discord.Member):
            msg = f"{self.emotes[logtype]} **__User {logtype.title()}d:__** {author.mention} | {author.name}#{author.discriminator} {logtype}d {target.mention} | {target.name}#{target.discriminator}\n{self.emotes['id']} User ID: {target.id}"
            if reason is not None:
                msg += f"\n{self.emotes['reason']} Reason: {reason}"

        elif isinstance(target, discord.TextChannel):
            msg = f"{self.emotes[logtype]} **__Channel {logtype.title()}ed:__** {author.mention} | {author.name}#{author.discriminator} {logtype}ed {target.mention} | {target.name}\n{self.emotes['id']} Channel ID: {target.id}"
            if logtype == 'clear':
                msg += f"\n{self.emotes['discriminator']} Number of messages cleared: {kwargs['numofmessages']}"

            if reason is not None:
                msg += f"\n{self.emotes['reason']} Reason: {reason}"

        elif isinstance(target, discord.Role):
            msg = f"{self.emotes[logtype]} **__Role {logtype.title()}ed:__** {author.mention} | {author.name}#{author.discriminator} {logtype}ed {escape_mentions(target.mention)} | {target.name}\n{self.emotes['id']} Role ID: {target.id}"
            if reason is not None:
                msg += f"\n{self.emotes['reason']} Reason: {reason}"

        elif isinstance(target, discord.Member) or isinstance(target, discord.User):
            msg = f"{self.emotes[logtype]} **__User {logtype.title()}ed:__** {author.mention} | {author.name}#{author.discriminator} {logtype}ed {target.mention} | {target.name}#{target.discriminator}\n{self.emotes['id']} User ID: {target.id}"
            if reason is not None:
                msg += f"\n{self.emotes['reason']} Reason: {reason}"
        else:
            raise errors.loggingError(logtype, "No ifs were triggered")

        try:
            await self.dispatch("modlogs", ctx.guild, logtype, msg)
        except errors.loggingError:
            pass

    async def warnclear(self, ctx, logtype, member: typing.Union[discord.Member, discord.User], author, warn=None):
        if warn is None:
            msg = f"{self.emotes['clear']} **__Cleared Warns__** {member.mention} | {member}#{member.discriminator} had their warns cleared by {author.mention} | {author.name}#{author.discriminator}\n{self.emotes['id']} User ID: {member.id}"
            embed = None
        else:
            msg = f"{self.emotes['clear']} **__Cleared Warn__** {member.mention} | {member.name}#{member.discriminator} had warnid {warn.id} removed by {author.mention} | {author.name}#{author.discriminator}\n{self.emotes['id']} User ID: {member.id}"
            embed = discord.Embed(color=0xe6ff33)
            embed.set_author(name=f"{member}", icon_url=member.avatar_url)
            embed.add_field(name=f"\n\n{warn.time_stamp}",
                            value=f"{warn.reason if warn.reason is not None else 'No reason given for warn'}\n Issuer: {self.bot.get_user(warn.authorid) if self.bot.get_user(warn.authorid) is not None else self.bot.fetch_user(warn.authorid)}")

        try:
            await self.dispatch('modlogs', author.guild, logtype, msg, embed)
        except errors.loggingError:
            await ctx.send("Please configure logging for modlogs using `[p]logchannel set modlogs #<yourchannel>`")

    async def slowmodelog(self, channel: discord.TextChannel, time: str, author: discord.Member, reason=None):
        """Slowmode logging"""
        msg = f"{self.emotes['slowmode']} **__Channel Slowed:__** {author.mention} | {channel} added a {time} delay to {channel.mention}\n{self.emotes['id']} Channel ID: {channel.id}"
        if reason:
            msg += f"\n{self.emotes['reason']} Reason: {reason}"

        await self.dispatch("modlogs", author.guild, 'slowmode', msg)

    async def automod(self, logtype, member: discord.Member, reason=None):
        """auto moderation logging, WIP"""
        msg = f"{self.emotes[logtype]} **__Auto-{logtype}:__** {member.mention} | {member.name}#{member.discriminator}\n{self.emotes['id']} User ID: {member.id}"
        if reason:
            msg += f"\n{self.emotes['reason']} Reason: {reason}"

        try:
            await self.dispatch('modlogs', member.guild, logtype, msg)
        except errors.loggingError:
            pass

    async def softbanJoin(self, member: discord.Member, author: discord.Member, reason=None):
        """Softban logging"""
        if reason is not None:
            reason = escape_mentions(reason)
        msg = f"{self.emotes['failure']} **__Attempted Join:__** {member.mention} | {member.name}#{member.discriminator} tried to join {member.guild.name} but is softbanned by {author}\n{self.emotes['id']} User ID: {member.id}"
        if reason:
            msg += f"\n{self.emotes['reason']} Reason: `{reason}.`"

        try:
            await self.dispatch("modlogs", member.guild, "ban", msg)
        except errors.loggingError:
            pass

    async def userUpdate(self, logtype, userbefore, userafter):
        """User updates, agnostic to servers"""
        msg = f"{self.emotes[logtype]} **__User Update:__** A user has updated their {logtype}: `{userbefore}` -> `{userafter}`!\n{self.emotes['id']} User ID: {userafter.id}\n"
        for g in self.bot.guilds:
            if userafter in g:
                channel = g.get_channel(
                    self.bot.db.fetchval("SELECT memberlogs FROM log_channels WHERE guildid = $1", g.id))
                if not channel:
                    continue
                else:
                    await channel.send(msg)

    async def memberUpdate(self, logtype, member, beforechange, afterchange):
        msg = f"{self.emotes[logtype]} **__Member Update:__** {member.name}#{member.discriminator}'s {logtype} was updated\n{self.emotes['id']} User ID: {member.id}\n{self.emotes['username']} Change: `{beforechange}` -> `{afterchange}`"

        try:
            await self.dispatch("memberlogs", member.guild, logtype, msg)
        except errors.loggingError:
            pass

    async def roleUpdate(self, logtype, before: discord.Member, after: discord.Member):
        roles_before = before.roles[1:]
        roles_after = after.roles[1:]
        role_string = ""

        if logtype == 'remove role':
            for role in roles_before:
                if role not in roles_after:
                    role_string += f" __~~*{role.name}*~~__,"
                else:
                    role_string += f" {role.name},"

        elif logtype == 'add role':
            for role in roles_after:
                if role not in roles_before:
                    role_string += f" _**{role.name}**_,"
                else:
                    role_string += f" {role.name},"

        role_string = role_string[:-1]

        msg = f"{self.emotes['info']} **__Role Update:__** {after.name}#{after.discriminator} had their roles updated!\n{self.emotes['id']} User ID: {after.id}\n{self.emotes[logtype]} {logtype.title()}: " + role_string

        try:
            await self.dispatch("memberlogs", after.guild, logtype, msg)
        except errors.loggingError:
            pass

    async def joinleaveLogs(self, logtype: str, member: discord.Member):
        """logs members joining and leaving"""
        msg = f"{self.emotes[logtype]} **__Member " + (
            "Left:__**" if logtype == 'left' else f"{logtype.title()}ed:__**") + f" {member.mention} | {member.name}#{member.discriminator}" + f"\n{self.emotes['id']} User ID: {member.id}\n{self.emotes['creationdate']} Account Creation: {member.created_at}"

        try:
            await self.dispatch("memberlogs", member.guild, logtype, msg)
        except errors.loggingError:
            pass

    async def messageEditLogs(self, logtype: str, before: discord.Message, after: discord.Message) -> str:
        """Logs a message edit"""
        msg = f"{self.emotes[logtype]} **__Message Edited:__** {after.author.name}#{after.author.discriminator} edited their message in {after.channel.mention}\n{self.emotes['id']} User ID: {after.author.id}\n{self.emotes['message']}Before: `{before.content}` -> After: `{after.content}`\n:link: Link: https://discordapp.com/channels/{after.guild.id}/{after.channel.id}/{after.id}"

        try:
            await self.dispatch("messagelogs", after.guild, logtype, msg)
        except errors.loggingError:
            pass

    async def messageDeletion(self, logtype: str, message: discord.Message):
        msg = f"{self.emotes[logtype]} **__Message Deleted:__** {message.author.name}#{message.author.discriminator} deleted their message in {message.channel.mention}\n{self.emotes['id']} User ID: {message.author.id}\n{self.emotes['message']} Content: ```{message.content}```"

        try:
            await self.dispatch("messagelogs", message.guild, logtype, msg)
        except errors.loggingError:
            pass

    async def messagepinned(self, logtype: str, pinner, message: discord.Message):
        msg = f"{self.emotes[logtype]} **__Message {logtype.title()}ned__** {pinner} {logtype}ned a message to {message.channel.mention}\n{self.emotes['id']} User ID: {message.author.id}\n{self.emotes['message']} Content: ```{message.content}```\n:link: Link: https://discordapp.com/channels/{message.guild.id}/{message.channel.id}/{message.id}"

        try:
            await self.dispatch("messagelogs", message.guild, logtype, msg)
        except errors.loggingError:
            pass

    async def logsetup(self, logtype: str, action: str, member: discord.Member,
                       item: typing.Union[discord.TextChannel, discord.Role], dbItem: str):

        msg = f"{self.emotes[logtype]} **__{logtype.title()} {action.title()}__** {member.name}#{member.discriminator} {logtype} {escape_mentions(item.mention) if isinstance(item, discord.Role) else item.mention} to the {action}\n {self.emotes['id']} {action.title()} ID: {item.id}"

        await self.dispatch(dbItem, item.guild, logtype, msg)

    async def togglelogsetup(self, logtype: str, action: str, member: discord.Member, dbItem: str):

        enabledisable = 'enabled' if logtype == 'set' else 'disabled'
        msg = f"{self.emotes[logtype]} **__{enabledisable.title()} {action.title()}:__** {member.name}#{member.discriminator} {enabledisable} {action}"

        await self.dispatch(dbItem, member.guild, logtype, msg)

    async def notice(self, logtype, author: discord.Member, message, dbChan: str):
        """Misc logging"""
        if not dbChan in ('modlogs', 'memberlogs', 'messagelogs', 'auditlogs'):
            consoleLogger.warn(f"Unable to log notice log on guild {author.guild.name} message: `{message}`")

        else:
            msg = f"{self.emotes[logtype]} **__Notice__** {author.name}#{author.discriminator} run a command and: `{message}`"

            try:
                await self.dispatch(dbChan, author.guild, logtype, msg)
            except errors.loggingError:
                pass

    # add audit log logging

    async def unsoftban(self, ctx, member):
        msg = f"{self.emotes['warn']} **__Unsoftban:__** {member.mention} | {member.name}#{member.discriminator}\n{self.emotes['id']} User ID: {member.id}"  # TODO add audit log intergation

        try:
            await self.dispatch('modlogs', ctx.guild, 'unban', msg)
        except errors.loggingError:
            await ctx.send("Please configure logging for modlogs using `[p]logchannel set modlogs #<yourchannel>`")
