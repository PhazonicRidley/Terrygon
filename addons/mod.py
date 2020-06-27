import discord
from discord.ext import commands
from logzero import setup_logger
import typing
from utils import checks, common

# set up logging instance
modmoduleconsolelogger = setup_logger(name='mod command logs', logfile='logs/mod.log', maxBytes=1000000)


class Mod(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    # mute commands
    @checks.is_staff_or_perms("Mod", manage_roles=True)
    @commands.command()
    async def mute(self, ctx, member: discord.Member, *, reason: str = None):
        modandbotprotection = await checks.modAndBotProtection(self.bot, ctx, member, "mute")
        if modandbotprotection is not None:
            await ctx.send(modandbotprotection)
            return

        async with self.bot.db.acquire() as conn:
            mutedroleid = (await conn.fetchrow("SELECT mutedRole FROM roles WHERE guildID = $1", ctx.guild.id))[0]
            if mutedroleid is None:
                await ctx.send("Muted role not configured! Please configure it with dbrole set muterole <roleid>")
                return

            muted_role = ctx.guild.get_role(mutedroleid)

            try:
                if muted_role in member.roles or (
                        await conn.fetchrow("SELECT userID FROM mutes WHERE userID = $1 AND guildID = $2", member.id,
                                            ctx.guild.id))[0] == member.id:
                    await ctx.send("User is already muted")
                    return
            except TypeError:
                pass

            try:
                await member.add_roles(muted_role)
            except discord.Forbidden:
                await ctx.send("💢 I dont have permission to do this.")
                return

            await conn.execute("INSERT INTO mutes (userID, authorID, guildID, reason) VALUES ($1, $2, $3, $4)",
                               member.id, ctx.author.id, ctx.guild.id, reason)

            msg = f"You have been muted in {ctx.guild.name}"
            if reason is not None:
                msg += f" for the following reason: {reason}"

            try:
                await member.send(msg)
            except discord.Forbidden:
                pass
            await self.bot.discordLogger.modlogs(ctx, 'mute', member, ctx.author, reason)

            await ctx.send(f"{member} has been muted.")

    @checks.is_staff_or_perms("Mod", manage_roles=True)
    @commands.command()
    async def unmute(self, ctx, member: discord.Member, *, reason: str = None):
        modandbotprotection = await checks.modAndBotProtection(self.bot, ctx, member, "unmute")
        if modandbotprotection is not None:
            await ctx.send(modandbotprotection)
            return

        async with self.bot.db.acquire() as conn:
            mutedroleid = (await conn.fetchrow("SELECT mutedRole FROM roles WHERE guildID = $1", ctx.guild.id))[0]
            if mutedroleid is None:
                await ctx.send("Muted role not configured! Please configure it with dbrole set muterole <roleid>")
                return

            muted_role = ctx.guild.get_role(mutedroleid)

            try:
                if not muted_role in member.roles or not (await conn.fetchrow(
                        "SELECT userID FROM mutes WHERE userID = $1 AND guildID = $2", member.id, ctx.guild.id))[
                                                             0] == member.id:
                    await ctx.send("User is not muted")
                    return
            except TypeError:
                pass

            try:
                await member.remove_roles(muted_role)
            except discord.Forbidden:
                await ctx.send("💢 I dont have permission to do this.")
                return

            await conn.execute("DELETE FROM mutes WHERE userID = $1 AND guildID = $2", member.id, ctx.guild.id)

            await self.bot.discordLogger.modlogs(ctx, 'unmute', member, ctx.author, reason)

            await ctx.send(f"{member} has been unmuted.")

        # lockdown commands

    @checks.is_staff_or_perms("Mod", manage_channels=True)
    @commands.command(aliases=['lock'], )
    async def lockdown(self, ctx, channel: discord.TextChannel = None, *, reason=None):
        """Locks a channel"""
        async with self.bot.db.acquire() as conn:
            if await conn.fetchval("SELECT approvalSystem FROM guild_settings WHERE guildID = $1", ctx.guild.id):
                try:
                    base_role = ctx.guild.get_role(
                        await conn.fetchval("SELECT approvedRole FROM roles WHERE guildID = $1", ctx.guild.id))
                except TypeError:
                    modmoduleconsolelogger.warn(
                        f"Unable to lock approval role on guild {ctx.guild.name}, it doesnt exist in the database! locking the default everyone role instead")
                    self.bot.discordLogger.notice('notice', ctx.author,
                                                  f"Unable to lock {ctx.channel.mention} for the approval role as it was not found in the database! locking the default everyone role instead")
                    base_role = ctx.guild.default_role
            else:
                base_role = ctx.guild.default_role

        if channel is None:
            channel = ctx.channel

        else:
            await ctx.send(f"{self.bot.discordLogger.emotes['lock']} {channel.mention} has been locked.")

        try:

            await channel.set_permissions(base_role, send_messages=False)
            chanmsg = f"{self.bot.discordLogger.emotes['lock']} Channel locked."
            if reason is not None:
                chanmsg += f" The reason is `{reason}`"
            await channel.send(chanmsg)
            await self.bot.discordLogger.modlogs(ctx, "lock", channel, ctx.author, reason)

        except discord.Forbidden:
            await ctx.send("I don't have permission to lock channels!")

    @checks.is_staff_or_perms("Mod", manage_channels=True)
    @commands.command(aliases=['unlock'], )
    async def unlockdown(self, ctx, channel: discord.TextChannel = None):
        """Unlocks a channel"""
        async with self.bot.db.acquire() as conn:
            if await conn.fetchrow("SELECT approvalSystem FROM guild_settings WHERE guildID = $1", ctx.guild.id):
                try:
                    base_role = ctx.guild.get_role(
                        await conn.fetchval("SELECT approvedRole FROM roles WHERE guildID = $1", ctx.guild.id))
                except TypeError:
                    modmoduleconsolelogger.warn(
                        f"Unable to unlock approval role on guild {ctx.guild.name}, it doesnt exist in the database! unlocking the default everyone role instead")
                    self.bot.discordLogger.notice('notice', ctx.author,
                                                  f"Unable to unlock {ctx.channel.mention} for the approval role as it was not found in the database! unlocking the default everyone role instead")
                    base_role = ctx.guild.default_role
            else:
                base_role = ctx.guild.default_role

        if channel is None:
            channel = ctx.channel
            cmdinchan = True

        else:
            cmdinchan = False

        try:

            await channel.set_permissions(base_role, send_messages=True)
            chanmsg = f"{self.bot.discordLogger.emotes['unlock']} Channel unlocked."
            await channel.send(chanmsg)
            await self.bot.discordLogger.modlogs(ctx, "unlock", channel, ctx.author, None)

            if not cmdinchan:
                await ctx.send(f"{self.bot.discordLogger.emotes['unlock']} {channel.mention} has been unlocked.")

        except discord.Forbidden:
            await ctx.send("I don't have permission to unlock channels!")

    # kick and ban commands

    async def removefromapprovallist(self, member: discord.Member, guild: discord.Guild):
        async with self.bot.db.acquire() as conn:
            if not await conn.fetchval("SELECT approvalsystem FROM guild_settings WHERE guildid = $1", guild.id):
                return
            else:
                if not await conn.fetchval("SELECT * FROM approvedmembers WHERE guildid = $1 AND userid = $2", guild.id,
                                           member.id):
                    return
                else:
                    await conn.fetchval("DELETE FROM approvedmembers WHERE userid = $1 AND guildid = $2", member.id,
                                        guild.id)

    @checks.is_staff_or_perms("Mod", kick_members=True)
    @commands.command()
    async def kick(self, ctx, member: discord.Member, *, reason: str = None):
        """Kick a member. (Mod+)"""
        modandbotprotection = await checks.modAndBotProtection(self.bot, ctx, member, "kick")
        if modandbotprotection is not None:
            await ctx.send(modandbotprotection)
            return

        msg = f"You have been kicked from {ctx.guild.name}"
        if reason:
            msg += f" for the following reason: `{reason}`"

        try:
            try:
                await member.send(msg)
            except discord.Forbidden:
                pass

            await self.removefromapprovallist(member, ctx.guild)
            await member.kick(reason=reason if reason is not None else "No reason given")
        except discord.Forbidden:
            await ctx.send("Unable to kick discord.Member, check my permissions!")
            return

        await ctx.send(f"{member.name}#{member.discriminator} has been kicked {self.bot.discordLogger.emotes['kick']}")
        await self.bot.discordLogger.modlogs(ctx, 'kick', member, ctx.author, reason)

    @checks.is_staff_or_perms("Admin", ban_members=True)
    @commands.guild_only()
    @commands.command(aliases=['yeet'], )
    async def ban(self, ctx, member: typing.Union[discord.Member, int], *, reason: str = None):
        """Ban a member. (Admin+)"""
        if isinstance(member, int):
            try:
                member = await self.bot.fetch_user(member)  # calls the api to find and ban the user
            except discord.NotFound:
                return await ctx.send("User was not found")
        else:
            modandbotprotection = await checks.modAndBotProtection(self.bot, ctx, member, "ban")
            if modandbotprotection is not None:
                await ctx.send(modandbotprotection)
                return

        if isinstance(member, discord.Member):

            msg = f"You have been banned from {ctx.guild.name}"
            if reason:
                msg += f" for the following reason: `{reason}`"

            try:
                await member.send(msg)
            except discord.Forbidden:
                pass

            await self.removefromapprovallist(member, ctx.guild)

        try:
            await ctx.guild.ban(member, reason=reason if reason is not None else "No reason given")
        except discord.Forbidden:
            await ctx.send("Unable to ban discord.Member")
            return

        await ctx.send(f"{member.name}#{member.discriminator} has been banned {self.bot.discordLogger.emotes['ban']}")
        await self.bot.discordLogger.modlogs(ctx, 'ban', member, ctx.author, reason)

    @checks.is_staff_or_perms("Admin", ban_members=True)
    @commands.command()
    async def softban(self, ctx, member: typing.Union[discord.Member, int], *, reason: str = None):

        if isinstance(member, int):
            member = await self.bot.fetch_user(member)

        elif isinstance(member, discord.Member):
            modandbotprotection = await checks.modAndBotProtection(self.bot, ctx, member, "softban")
            if modandbotprotection is not None:
                await ctx.send(modandbotprotection)
                return

            msg = f"You have been softbanned from {ctx.guild.name}"
            if reason:
                msg += f"\nThe reason is: `{reason}`"

            try:
                try:
                    await member.send(msg)
                except discord.Forbidden:
                    pass

                await self.removefromapprovallist(member, ctx.guild)
                await member.kick(
                    reason="softbanned:" + f"The reason is {reason}" if reason is not None else "No given reason")
            except discord.Forbidden:
                await ctx.send("Unable to softban member")

        async with self.bot.db.acquire() as conn:
            await conn.execute("INSERT INTO bans (userID, authorid, guildID, reason) VALUES ($1, $2, $3, $4)",
                               member.id, ctx.author.id, ctx.guild.id, reason)

        await ctx.send(
            f"{member.name}#{member.discriminator} has been softbanned {self.bot.discordLogger.emotes['ban']}")
        await self.bot.discordLogger.modlogs(ctx, 'softban', member, ctx.author, reason)

    @checks.is_staff_or_perms("Admin", ban_members=True)
    @commands.command()
    async def unsoftban(self, ctx, user: int):
        member = await self.bot.fetch_user(user)
        async with self.bot.db.acquire() as conn:
            if await conn.fetchval("SELECT * FROM bans WHERE userid = $1 AND guildid = $2", member.id, ctx.guild.id):
                await conn.execute("DELETE FROM bans WHERE userid = $1 AND guildid = $2",
                                   member.id, ctx.guild.id)
            else:
                return await ctx.send("User is not softbanned")

        await ctx.send(
            f"{member.name}#{member.discriminator} has been unsoftbanned {self.bot.discordLogger.emotes['warn']}")

        await self.bot.discordLogger.unsoftban(ctx, member)

    @checks.is_staff_or_perms('Mod', manage_channels=True)
    @commands.command()
    async def clear(self, ctx, numOfMessages: int, *, reason: str = None):
        """Clears messages from a chat (Mod+ or manage channels)"""
        if numOfMessages > 100:
            return await ctx.send("You cannot clear that many messages!")
        else:
            await ctx.channel.purge(limit=numOfMessages + 1)

        await self.bot.discordLogger.modlogs(ctx, 'clear', ctx.channel, ctx.author, reason, numofmessages=numOfMessages)


    @checks.is_staff_or_perms("Mod", manage_channels=True)
    @commands.command()
    async def slowmode(self, ctx, channel: discord.TextChannel, slowtime, *, reason = None):
        """Slows a channel, set slowtime to 0 to disable (Mod+ or manage channels)"""
        slowtimeseconds = common.parse_time(slowtime)
        if slowtimeseconds == -1:
            return await ctx.send("Invalid time format")

        if slowtimeseconds >= 21600:
            return await ctx.send("You cannot set a slowmode to 6 hours or higher")

        try:
            await channel.edit(slowmode_delay=slowtimeseconds)
            await ctx.send(f"Slowmode of {slowtime} set to {channel.mention}")
        except discord.Forbidden:
            return await ctx.send("I don't have permission to update the slowmode delay")

        await self.bot.discordLogger.slowmodelog(channel, slowtime, ctx.author, reason)



def setup(bot):
    bot.add_cog(Mod(bot))
