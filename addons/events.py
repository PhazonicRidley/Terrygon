import discord
from discord.ext import commands
from utils import checks
from logzero import logger as consolelogger, logfile

logfile("logs/events.log", maxBytes=1e6)


class Events(commands.Cog):
    """
    Events for the bot
    """

    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_user_update(self, before, after):
        if before.name != after.name:
            await self.bot.discordLogger.memberUpdate("username", after, before.username, after.username)

        if before.discriminator != after.discriminator:
            await self.bot.discordLogger.memberUpdate("discriminator", after, before.discriminator, after.discriminator)

    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        # makes sure logging is set up
        if not await self.bot.isLogRegistered(after.guild, "memberlogs"):
            return

        if before.nick != after.nick:
            await self.bot.discordLogger.memberUpdate("nickname", after, before.nick, after.nick)

        # role changes
        if len(before.roles) > len(after.roles):
            await self.bot.discordLogger.roleUpdate("remove role", before, after)
        elif len(after.roles) > len(before.roles):
            await self.bot.discordLogger.roleUpdate("add role", before, after)

    async def addGuild(self, newGuild):
        async with self.bot.db.acquire() as conn:
            schemalist = ['log_channels', 'roles', 'guild_settings', 'trustedusers']
            for table in schemalist:
                try:
                    await conn.execute(f"INSERT INTO {table} (guildid) VALUES ($1)", newGuild.id)
                except Exception:
                    pass

    # join leave logs
    @commands.Cog.listener()
    async def on_member_join(self, member):
        if not await self.bot.isLogRegistered(member.guild, "memberlogs"):
            logs = False

        else:
            logs = True

        async with self.bot.db.acquire() as conn:

            # check if member is approved if needed
            if await conn.fetchval("SELECT approvalsystem FROM guild_settings WHERE guildid = $1", member.guild.id):
                if await conn.fetchval("SELECT userid FROM approvedmembers WHERE userid = $1 AND guildid = $2",
                                       member.id, member.guild.id):
                    try:
                        approvedrole = member.guild.get_role(
                            await conn.fetchval("SELECT approvedrole FROM roles WHERE guildid = $1", member.guild.id))
                        await member.add_roles(approvedrole)
                    except Exception:
                        pass

            # check for softbans
            if await conn.fetchval("SELECT userID FROM bans WHERE userID = $1 AND guildID = $2",
                                   member.id, member.guild.id):
                try:
                    issuerid = await conn.fetchval("SELECT authorID FROM bans WHERE userID = $1 AND guildID = $2",
                                                   member.id, member.guild.id)
                    reason = await conn.fetchval("SELECT reason FROM bans WHERE userID = $1 AND guildID = $2",
                                                 member.id, member.guild.id)
                except TypeError:
                    reason = None

                dmmsg = f"You have been softbanned from {member.guild.name}"
                if reason:
                    dmmsg += f" For the reason {reason}"
                try:
                    await member.send(dmmsg)
                except discord.Forbidden:
                    reason += " `Message not sent to user`"

                if logs:
                    await self.bot.discordLogger.softbanJoin(member, self.bot.get_user(issuerid) if self.bot.get_user(
                        issuerid) is not None else await self.bot.fetch_user(issuerid), reason)

                try:
                    await member.kick(
                        reason="softban" + f", the reason is: {reason}" if reason is not None else "No reason")
                    return
                except discord.Forbidden:
                    consolelogger.warning(f"Unable to kick user in softban join on {member.guild.name}, check perms")

            # check if member is muted
            try:
                muted = await conn.fetchval("SELECT userID FROM mutes WHERE userID = $1 AND guildID = $2", member.id,
                                            member.guild.id)
            except TypeError:
                muted = None
            if muted is not None:
                try:
                    guildMuteRoleid = await conn.fetchval("SELECT mutedrole FROM roles WHERE guildID = $1",
                                                          member.guild.id)
                except TypeError:
                    return  # this only is called if None is gotten from the above query

                await member.add_roles(member.guild.get_role(guildMuteRoleid))

            if await conn.fetchval("SELECT enableJoinLeaveLogs FROM guild_settings WHERE guildID = $1",
                                   member.guild.id) and logs:
                await self.bot.discordLogger.joinleaveLogs("join", member)

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        if not await self.bot.isLogRegistered(member.guild, "memberlogs"):
            return

        if await self.bot.db.fetchval("SELECT enableJoinLeaveLogs FROM guild_settings WHERE guildID = $1", member.guild.id):
            await self.bot.discordLogger.joinleaveLogs("left", member)

    # message logs
    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        if not await self.bot.isLogRegistered(after.guild, "messagelogs"):
            return

        if before.content == after.content:
            return

        if after.author.bot:
            return
    
        if await self.bot.db.fetchval("SELECT enableCoreMessageLogs FROM guild_settings WHERE guildID = $1", after.guild.id):
            await self.bot.discordLogger.messageEditLogs("msgedit", before, after)

    @commands.Cog.listener()
    async def on_message_delete(self, message):
        if not await self.bot.isLogRegistered(message.guild, "messagelogs"):
            return

        if await self.bot.db.fetchval("SELECT enableCoreMessageLogs FROM guild_settings WHERE guildID = $1", message.guild.id):
            await self.bot.discordLogger.messageDeletion("mdelete", message)

    @commands.Cog.listener()
    async def on_guild_join(self, newGuild):
        await self.addGuild(newGuild)

    @checks.is_bot_owner()
    @commands.command()
    async def autoguildadd(self, ctx):
        """Automatically tries to add every guild the bot is in to the database, if they're already in there, nothing happens"""
        for guild in self.bot.guilds:
            await self.addGuild(guild)
        await ctx.send("Added all guilds to the database!")

    @checks.is_bot_owner()
    @commands.command()
    async def manualguildadd(self, ctx, newGuildid):
        newGuild = await self.bot.fetch_guild(newGuildid)
        await self.addGuild(newGuild)
        await ctx.send(f"Guild {newGuild.name} added to the database manually")

    @checks.is_bot_owner()
    @commands.command()
    async def manualguildremove(self, ctx, guildid):
        # fully removes a guild and its data
        guild = await self.bot.fetch_guild(guildid)
        async with self.bot.db.acquire() as conn:
            schemalist = await conn.fetch(
                "SELECT table_name FROM information_schema.columns WHERE column_name = 'guildid'")
            for table in schemalist:
                try:
                    await conn.execute(f"DELETE FROM {table[0]} WHERE guildid = $1", guild.id)
                except Exception:
                    pass

        await ctx.send(f"Guild {guild.name} removed")

        # add audit log logs


def setup(bot):
    bot.add_cog(Events(bot))
