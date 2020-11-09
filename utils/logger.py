import typing

import discord
import logzero
from discord.utils import escape_mentions
from logzero import logger as console_logger

from addons import mod
from utils import errors

logzero.logfile("logs/discord_logger.log", maxBytes=1e6)


class Logger:

    def __init__(self, bot):
        self.bot = bot
        # TODO temp emoji dict for logging, will convert to full sql database json thingy later
        self.emotes = {
            # mod actions
            'ban': "\U000026d4",
            'kick': "\U0001f462",
            'mute': "\U0001f507",
            'unmute': "\U0001f50a",
            'warn': "\U000026a0",
            'approve': "\U0001f44d",
            "unapprove": "\U0001f44e",
            "lock": ":lock:",
            "unlock": "\U0001f513",
            "clear": "\U0001f5d1",
            "slowmode": "\U0001f551",
            "block": "\U0001f6ab",
            "unblock": "\U00002705",
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

    async def dispatch(self, database_channel, guild: discord.Guild, log_type, msg, embed: discord.Embed = None):
        """Sends the logging message off to the registered channel"""
        if not database_channel in ("modlogs", "memberlogs", "messagelogs", "auditlogs"):
            raise errors.loggingError(log_type, database_channel)

        query = f"SELECT {database_channel} FROM log_channels WHERE guildID = $1"
        async with self.bot.db.acquire() as conn:

            channel_id = await conn.fetchval(query, guild.id)
            if channel_id is None:
                raise errors.loggingError(log_type, guild)

            else:
                log_channel = self.bot.get_channel(channel_id)
                if log_channel is None:
                    console_logger.error("Did not parse asyncpg record object properly.")
                else:
                    await log_channel.send(msg)
                    if embed:
                        await log_channel.send(embed=embed)

    async def mod_logs(self, ctx, log_type: str, target: typing.Union[discord.Member, discord.TextChannel, discord.Role], author: discord.Member, reason=None, **kwargs):
        """Logs bans, kicks, mutes, unmutes, warns, and other moderation actions in the mod logs channel"""

        # logs bans and soft bans
        if log_type == 'ban' or log_type == 'softban':
            logging_msg = f"{self.emotes['ban']} **__User {log_type.title()}ned:__** {author.mention} | {author.name}#{author.discriminator} {log_type}ned {target.mention} | {target.name}#{target.discriminator}\n{self.emotes['id']} User ID: {target.id}"
            if reason is not None:
                logging_msg += f"\n{self.emotes['reason']}Reason: {reason}"

        # logs mutes, unmutes, approves, and unapproves.
        elif (log_type == 'mute' or log_type == 'unmute' or log_type == 'approve' or log_type == 'unapprove') and isinstance(target, discord.Member):
            logging_msg = f"{self.emotes[log_type]} **__User {log_type.title()}d:__** {author.mention} | {author.name}#{author.discriminator} {log_type}d {target.mention} | {target.name}#{target.discriminator}\n{self.emotes['id']} User ID: {target.id}"
            if reason is not None:
                logging_msg += f"\n{self.emotes['reason']} Reason: {reason}"

        # logs lockdowns and channel clears
        elif isinstance(target, discord.TextChannel):
            logging_msg = f"{self.emotes[log_type]} **__Channel {log_type.title()}ed:__** {author.mention} | {author.name}#{author.discriminator} {log_type}ed {target.mention} | {target.name}\n{self.emotes['id']} Channel ID: {target.id}"
            if log_type == 'clear':
                logging_msg += f"\n{self.emotes['discriminator']} Number of messages cleared: {kwargs['num_messages']}"

            if reason is not None:
                logging_msg += f"\n{self.emotes['reason']} Reason: {reason}"

        #elif isinstance(target, discord.Role):
          #  logging_msg = f"{self.emotes[log_type]} **__Role {log_type.title()}ed:__** {author.mention} | {author.name}#{author.discriminator} {log_type}ed {escape_mentions(target.mention)} | {target.name}\n{self.emotes['id']} Role ID: {target.id}"
          #  if reason is not None:
           #     logging_msg += f"\n{self.emotes['reason']} Reason: {reason}"

        # catch for all member actions that don't have special past participles
        elif isinstance(target, discord.Member) or isinstance(target, discord.User):
            logging_msg = f"{self.emotes[log_type]} **__User {log_type.title()}ed:__** {author.mention} | {author.name}#{author.discriminator} {log_type}ed {target.mention} | {target.name}#{target.discriminator}\n{self.emotes['id']} User ID: {target.id}"
            if reason is not None:
                logging_msg += f"\n{self.emotes['reason']} Reason: {reason}"
        else:
            raise errors.loggingError(log_type, "No ifs were triggered")

        try:
            await self.dispatch("modlogs", ctx.guild, log_type, logging_msg)
        except errors.loggingError:
            pass

    async def on_join_block(self, member, channels: list, embed: discord.Embed = None):
        logging_msg = f"{self.emotes['block']} **__User Auto-Blocked On Join:__**  {member.mention} | {member} has blocked from the following channels: `{', '.join(channels)}`\n{self.emotes['id']} User ID: {member.id}"

        await self.dispatch('modlogs', member.guild, 'block', logging_msg, embed)

    async def unblock_all_log(self, member, author, channels: list):
        logging_msg = f"{self.emotes['unblock']} **__User Unblocked Fully:__** {author.mention} has removed all blocks on {member.mention} | {member}. Blocked channels were: `{', '.join(channels)}`\n{self.emotes['id']} User ID: {member.id}"

        await self.dispatch('modlogs', member.guild, 'unblock', logging_msg)

    # TODO add timed functionality
    async def channel_block(self, log_type: str, member: discord.Member, author: discord.Member,
                            channel: typing.Union[discord.TextChannel, discord.VoiceChannel, discord.CategoryChannel], block_list: typing.List[str], reason: str = None):
        """Logs channel blocks"""
        channel_msg = ""
        if isinstance(channel, discord.CategoryChannel):
            channel_msg = f"the {channel.name} category."
        else:
            channel_msg = f"{channel.mention if isinstance(channel, discord.TextChannel) else channel.name}"

        logging_msg = f"{self.emotes[log_type]} **__User {log_type.title()}ed:__** {author.mention} has {log_type}ed {member.mention} | {member} from being able to `{'`, `'.join(block_list)}` in {channel_msg}\n{self.emotes['id']} User ID: {member.id}"
        if reason:
            logging_msg += f"\n{self.emotes['reason']} Reason: {reason}"

        await self.dispatch("modlogs", author.guild, log_type, logging_msg)

    async def warn_clear(self, log_type, member: typing.Union[discord.Member, discord.User], author, warn=None):
        """Logs the deletion of user warns."""
        if warn is None:
            logging_msg = f"{self.emotes['clear']} **__Cleared Warns__** {member.mention} | {member}#{member.discriminator} had their warns cleared by {author.mention} | {author.name}#{author.discriminator}\n{self.emotes['id']} User ID: {member.id}"
            embed = None
        else:
            logging_msg = f"{self.emotes['clear']} **__Cleared Warn__** {member.mention} | {member.name}#{member.discriminator} had warnid {warn.id} removed by {author.mention} | {author.name}#{author.discriminator}\n{self.emotes['id']} User ID: {member.id}"
            embed = discord.Embed(color=0xe6ff33)
            embed.set_author(name=f"{member}", icon_url=member.avatar_url)
            embed.add_field(name=f"\n\n{warn.time_stamp}",
                            value=f"{warn.reason if warn.reason is not None else 'No reason given for warn'}\n Issuer: {self.bot.get_user(warn.author_id) if self.bot.get_user(warn.author_id) is not None else self.bot.fetch_user(warn.author_id)}")
        try:
            await self.dispatch('modlogs', author.guild, log_type, logging_msg, embed)
        except errors.loggingError:
            pass

    async def slowmode_log(self, channel: discord.TextChannel, time: str, author: discord.Member, reason=None):
        """Slowmode logging"""
        logging_msg = f"{self.emotes['slowmode']} **__Channel Slowed:__** {author.mention} | {channel} added a {time} delay to {channel.mention}\n{self.emotes['id']} Channel ID: {channel.id}"
        if reason:
            logging_msg += f"\n{self.emotes['reason']} Reason: {reason}"

        await self.dispatch("modlogs", author.guild, 'slowmode', logging_msg)

    async def auto_mod(self, logtype, member: discord.Member, reason=None):
        """auto moderation logging, WIP"""
        msg = f"{self.emotes[logtype]} **__Auto-{logtype}:__** {member.mention} | {member.name}#{member.discriminator}\n{self.emotes['id']} User ID: {member.id}"
        if reason:
            msg += f"\n{self.emotes['reason']} Reason: {reason}"

        try:
            await self.dispatch('modlogs', member.guild, logtype, msg)
        except errors.loggingError:
            pass

    async def softban_join(self, member: discord.Member, author: discord.Member, reason=None):
        """Softban logging"""
        logging_msg = f"{self.emotes['failure']} **__Attempted Join:__** {member.mention} | {member.name}#{member.discriminator} tried to join {member.guild.name} but is softbanned by {author}\n{self.emotes['id']} User ID: {member.id}"
        if reason:
            logging_msg += f"\n{self.emotes['reason']} Reason: `{reason}.`"

        try:
            await self.dispatch("modlogs", member.guild, "ban", logging_msg)
        except errors.loggingError:
            pass

    async def user_update(self, logtype, user: discord.User, user_before, user_after):
        """User updates, agnostic to servers"""
        logging_msg = f"{self.emotes[logtype]} **__User Update:__** {user.mention} has updated their {logtype}\n{self.emotes['id']} User ID: {user.id}\n:pencil: `{user_before}` -> `{user_after}`"
        for g in self.bot.guilds:
            if user in g.members:
                channel = g.get_channel(
                    await self.bot.db.fetchval("SELECT memberlogs FROM log_channels WHERE guildid = $1", g.id))
                if not channel:
                    continue
                else:
                    await channel.send(logging_msg)

    async def member_update(self, logtype, member, before_change, after_change):
        logging_msg = f"{self.emotes[logtype]} **__Member Update:__** {member.name}#{member.discriminator}'s {logtype} was updated\n{self.emotes['id']} User ID: {member.id}\n{self.emotes['username']} Change: `{before_change}` -> `{after_change}`"

        try:
            await self.dispatch("memberlogs", member.guild, logtype, logging_msg)
        except errors.loggingError:
            pass

    async def role_update(self, log_type, before: discord.Member, after: discord.Member):
        roles_before = before.roles[1:]
        roles_after = after.roles[1:]
        role_string = ""

        if log_type == 'remove role':
            for role in roles_before:
                if role not in roles_after:
                    role_string += f" __~~*{role.name}*~~__,"
                else:
                    role_string += f" {role.name},"

        elif log_type == 'add role':
            for role in roles_after:
                if role not in roles_before:
                    role_string += f" __***{role.name}***__,"
                else:
                    role_string += f" {role.name},"

        role_string = role_string[:-1]

        logging_msg = f"{self.emotes['info']} **__Role Update:__** {after.name}#{after.discriminator} had their roles updated!\n{self.emotes['id']} User ID: {after.id}\n{self.emotes[log_type]} {log_type.title()}: " + role_string

        try:
            await self.dispatch("memberlogs", after.guild, log_type, logging_msg)
        except errors.loggingError:
            pass

    async def join_leave_logs(self, log_type: str, member: discord.Member):
        """logs members joining and leaving"""
        logging_msg = f"{self.emotes[log_type]} **__Member " + (
            "Left:__**" if log_type == 'left' else f"{log_type.title()}ed:__**") + f" {member.mention} | {member.name}#{member.discriminator}" + f"\n{self.emotes['id']} User ID: {member.id}\n{self.emotes['creationdate']} Account Creation: {member.created_at}"

        try:
            await self.dispatch("memberlogs", member.guild, log_type, logging_msg)
        except errors.loggingError:
            pass

    async def message_edit_logs(self, log_type: str, before: discord.Message, after: discord.Message) -> str:
        """Logs a message edit"""
        logging_msg = f"{self.emotes[log_type]} **__Message Edited:__** {after.author.name}#{after.author.discriminator} edited their message in {after.channel.mention}\n{self.emotes['id']} User ID: {after.author.id}\n{self.emotes['message']}Before: `{before.content}` -> After: `{after.content}`\n:link: Link: https://discordapp.com/channels/{after.guild.id}/{after.channel.id}/{after.id}"

        try:
            await self.dispatch("messagelogs", after.guild, log_type, logging_msg)
        except errors.loggingError:
            pass

    async def message_deletion(self, log_type: str, message: discord.Message):
        logging_msg = f"{self.emotes[log_type]} **__Message Deleted:__** {message.author.name}#{message.author.discriminator} deleted their message in {message.channel.mention}\n{self.emotes['id']} User ID: {message.author.id}\n{self.emotes['message']} Content: ```{message.content}```"

        try:
            await self.dispatch("messagelogs", message.guild, log_type, logging_msg)
        except errors.loggingError:
            pass

    async def message_pinned(self, log_type: str, pinner, message: discord.Message):
        logging_msg = f"{self.emotes[log_type]} **__Message {log_type.title()}ned__** {pinner} {log_type}ned a message to {message.channel.mention}\n{self.emotes['id']} User ID: {message.author.id}\n{self.emotes['message']} Content: ```{message.content}```\n:link: Link: https://discordapp.com/channels/{message.guild.id}/{message.channel.id}/{message.id}"

        try:
            await self.dispatch("messagelogs", message.guild, log_type, logging_msg)
        except errors.loggingError:
            pass

    async def log_setup(self, log_type: str, action: str, member: discord.Member,
                        item: typing.Union[discord.TextChannel, discord.Role], db_item: str):

        logging_msg = f"{self.emotes[log_type]} **__{log_type.title()} {action.title()}__** {member.name}#{member.discriminator} {log_type} {item.name if isinstance(item, discord.Role) else item.mention} to the {action}\n {self.emotes['id']} {action.title()} ID: {item.id}"

        await self.dispatch(db_item, item.guild, log_type, logging_msg)

    async def toggle_log_setup(self, log_type: str, action: str, member: discord.Member, db_item: str):

        enable_disable = 'enabled' if log_type == 'set' else 'disabled'
        logging_msg = f"{self.emotes[log_type]} **__{enable_disable.title()} {action.title()}:__** {member.name}#{member.discriminator} {enable_disable} {action}"

        await self.dispatch(db_item, member.guild, log_type, logging_msg)

    async def approval_config(self, author: discord.Member, approval_channel: discord.TextChannel,
                              approval_role: discord.Role):
        logging_msg = f"**__Approval System Configured:__** {author.mention} configured an approval system with {approval_channel.mention} as the gateway channel and {approval_role.name} as the role name.\n{self.emotes['id']} Channel ID: {approval_channel.id}\n{self.emotes['id']} Role ID: {approval_role.id}"
        await self.dispatch('modlogs', approval_channel.guild, 'approval system', logging_msg)

    async def approval_deletion(self, author: discord.Member, approval_channel: discord.TextChannel = None,
                                approval_role: discord.Role = None):  # turtle i will find you and i will make you step on a lego :blobgun:
        channel_role_msg = ""
        if approval_role:
            channel_role_msg += f"Approval Role: `{approval_role.name}`"
        if approval_channel:
            channel_role_msg += f", Approval Channel: `{approval_channel.name}`"
        logging_msg = f"**__Approval System Removed:__** {author.mention} has removed the approval system. {channel_role_msg}"

        await self.dispatch('modlogs', author.guild, 'approval system', logging_msg)

    # add audit log logging

    async def unsoftban_log(self, ctx, member):
        logging_msg = f"{self.emotes['warn']} **__Unsoftban:__** {member.mention} | {member.name}#{member.discriminator}\n{self.emotes['id']} User ID: {member.id}"

        try:
            await self.dispatch('modlogs', ctx.guild, 'unban', logging_msg)
        except errors.loggingError:
            await ctx.send("Please configure logging for modlogs using `[p]logchannel set modlogs #<yourchannel>`")



    async def auto_mod_setup(self, author: discord.Member, action: str, **kwargs):
        """Sets up auto-mod logging"""
        logging_msg = f"{self.emotes[action]} **__Auto-mod configured: {action.title()}__** {author.mention} has added an auto logging system for "
        if "warn_num" in kwargs.keys():
            logging_msg += f"when a user gets {kwargs['warn_num']} warn(s)."

        await self.dispatch('modlogs', author.guild, action, logging_msg)
