import discord
from discord.ext import commands
from utils import checks
from logzero import logger as console_logger, logfile

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
            await self.bot.discord_logger.user_update("username", after, before.name, after.name)

        if before.discriminator != after.discriminator:
            await self.bot.discord_logger.user_update("discriminator", after, before.discriminator, after.discriminator)

    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        # makes sure logging is set up
        if not await self.bot.is_log_registered(after.guild, "memberlogs"):
            return

        if before.nick != after.nick:
            await self.bot.discord_logger.member_update("nickname", after, before.nick, after.nick)

        # role changes
        if len(before.roles) > len(after.roles):
            await self.bot.discord_logger.role_update("remove role", before, after)
        elif len(after.roles) > len(before.roles):
            await self.bot.discord_logger.role_update("add role", before, after)

    async def add_guild(self, new_guild):
        async with self.bot.db.acquire() as conn:
            schema_list = ['log_channels', 'roles', 'guild_settings', 'trustedusers']
            for table in schema_list:
                try:
                    await conn.execute(f"INSERT INTO {table} (guildid) VALUES ($1)", new_guild.id)
                except Exception:
                    pass

    # join leave logs
    @commands.Cog.listener()
    async def on_member_join(self, member):
        if not await self.bot.is_log_registered(member.guild, "memberlogs"):
            logs = False

        else:
            logs = True

        async with self.bot.db.acquire() as conn:

            # check if member is approved if needed
            if await conn.fetchval("SELECT approvalsystem FROM guild_settings WHERE guildid = $1", member.guild.id):
                if await conn.fetchval("SELECT userid FROM approvedmembers WHERE userid = $1 AND guildid = $2",
                                       member.id, member.guild.id):
                    try:
                        approved_role = member.guild.get_role(
                            await conn.fetchval("SELECT approvedrole FROM roles WHERE guildid = $1", member.guild.id))
                        await member.add_roles(approved_role)
                    except Exception:
                        pass

            # check for softbans
            if await conn.fetchval("SELECT userID FROM bans WHERE userID = $1 AND guildID = $2",
                                   member.id, member.guild.id):
                try:
                    issuer_id = await conn.fetchval("SELECT authorID FROM bans WHERE userID = $1 AND guildID = $2",
                                                   member.id, member.guild.id)
                    reason = await conn.fetchval("SELECT reason FROM bans WHERE userID = $1 AND guildID = $2",
                                                 member.id, member.guild.id)
                except TypeError:
                    reason = None

                dm_msg = f"You have been softbanned from {member.guild.name}"
                if reason:
                    dm_msg += f" For the reason {reason}"
                try:
                    await member.send(dm_msg)
                except discord.Forbidden:
                    reason += " `Message not sent to user`"

                if logs:
                    await self.bot.discord_logger.softban_join(member, self.bot.get_user(issuer_id) if self.bot.get_user(
                        issuer_id) is not None else await self.bot.fetch_user(issuer_id), reason)

                try:
                    await member.kick(reason="softban" + f", the reason is: {reason}" if reason is not None else "No reason")
                    return
                except discord.Forbidden:
                    console_logger.warning(f"Unable to kick user in softban join on {member.guild.name}, check perms")

            # check if member is muted
            try:
                muted = await conn.fetchval("SELECT userID FROM mutes WHERE userID = $1 AND guildID = $2", member.id,
                                            member.guild.id)
            except TypeError:
                muted = None
            if muted is not None:
                try:
                    guild_mute_role_id = await conn.fetchval("SELECT mutedrole FROM roles WHERE guildID = $1", member.guild.id)
                except TypeError:
                    return  # this only is called if None is gotten from the above query

                await member.add_roles(member.guild.get_role(guild_mute_role_id))

            if await conn.fetchval("SELECT enableJoinLeaveLogs FROM guild_settings WHERE guildID = $1", member.guild.id) and logs:
                await self.bot.discord_logger.join_leave_logs("join", member)

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        if not await self.bot.is_log_registered(member.guild, "memberlogs"):
            return

        if await self.bot.db.fetchval("SELECT enableJoinLeaveLogs FROM guild_settings WHERE guildID = $1",
                                      member.guild.id):
            await self.bot.discord_logger.join_leave_logs("left", member)

    # message logs
    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        if not await self.bot.is_log_registered(after.guild, "messagelogs"):
            return

        if before.content == after.content:
            return

        if after.author.bot:
            return

        if await self.bot.db.fetchval("SELECT enableCoreMessageLogs FROM guild_settings WHERE guildID = $1", after.guild.id):
            await self.bot.discord_logger.message_edit_logs("msgedit", before, after)

    @commands.Cog.listener()
    async def on_message_delete(self, message):
        if not await self.bot.is_log_registered(message.guild, "messagelogs"):
            return

        if await self.bot.db.fetchval("SELECT enableCoreMessageLogs FROM guild_settings WHERE guildID = $1", message.guild.id):
            await self.bot.discord_logger.message_deletion("mdelete", message)

    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        await self.add_guild(guild)

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel):
        muted_role = await self.bot.db.fetchval("SELECT mutedrole FROM roles WHERE guildid = $1", channel.guild.id)
        muted_role = channel.guild.get_role(muted_role)
        if not muted_role:
            return
        kwargs = {
            'send_messages': False
        }

        if isinstance(channel, discord.CategoryChannel):
            kwargs.update({'connect': False})
        elif isinstance(channel, discord.VoiceChannel):
            del kwargs['send_messages']
            kwargs.update({'connect': False})

        try:
            channel.overwrites[muted_role]
        except KeyError:
            try:
                await channel.set_permissions(muted_role, **kwargs)
            except discord.Forbidden:
                return

        if await self.bot.db.fetchval("SELECT approvalSystem FROM guild_settings WHERE guildid = $1", channel.guild.id):
            approval_role = channel.guild.get_role(await self.bot.db.fetchval("SELECT approvedrole FROM roles WHERE guildid = $1", channel.guild.id))
            if not approval_role:
                return

            if channel.overwrites_for(channel.guild.default_role).read_messages is not False:
                try:
                    await channel.set_permissions(approval_role, read_messages=True)
                    await channel.set_permissions(channel.guild.default_role, read_messages=False)
                except discord.Forbidden:
                    return

    @checks.is_bot_owner()
    @commands.command(name="autoguildadd")
    async def auto_guild_add(self, ctx):
        """Automatically tries to add every guild the bot is in to the database, if they're already in there, nothing happens (Bot owner only)"""
        for guild in self.bot.guilds:
            await self.add_guild(guild)
        await ctx.send("Added all guilds to the database!")

    @checks.is_bot_owner()
    @commands.command(name="manualguildadd")
    async def manual_guild_add(self, ctx, new_guild_id):
        """Manually adds a guild to the database (Bot owner only)"""
        newGuild = await self.bot.fetch_guild(new_guild_id)
        await self.add_guild(newGuild)
        await ctx.send(f"Guild {newGuild.name} added to the database manually")

    @checks.is_bot_owner()
    @commands.command(name="manualguildremove")
    async def manual_guild_remove(self, ctx, guild_id):
        """Fully removes a guild and its data (Bot owner only)"""
        guild = await self.bot.fetch_guild(guild_id)
        async with self.bot.db.acquire() as conn:
            schema_list = await conn.fetch("SELECT table_name FROM information_schema.columns WHERE column_name = 'guildid'")
            for table in schema_list:
                try:
                    await conn.execute(f"DELETE FROM {table[0]} WHERE guildid = $1", guild.id)
                except Exception:
                    pass

        await ctx.send(f"Guild {guild.name} removed")


def setup(bot):
    bot.add_cog(Events(bot))
