import discord
from discord.ext import commands, flags
from logzero import setup_logger
import typing
from utils import checks, common, paginator

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
            mutedroleid = await conn.fetchval("SELECT mutedRole FROM roles WHERE guildID = $1", ctx.guild.id)
            if mutedroleid is None:
                cog = self.bot.get_cog('Setup')
                if not cog:
                    return await ctx.send(
                        "Set up cog not loaded and muted role not set, please manually set the muted role or load the setup cog to trigger the wizard")
                await cog.mutedrolesetup(ctx)

            mutedroleid = await conn.fetchval("SELECT mutedRole FROM roles WHERE guildID = $1", ctx.guild.id)
            if mutedroleid is None:
                return await ctx.send("No muted role found, please run the setup wizard for the muted role again")
            muted_role = ctx.guild.get_role(mutedroleid)
            if muted_role is None:
                await conn.execute("UPDATE roles SET mutedrole = NULL WHERE guildid = $1", ctx.guild.id)
                cog = self.bot.get_cog('Setup')
                if not cog:
                    return await ctx.send(
                        "Set up cog not loaded and muted role not set, please manually set the muted role or load the setup cog to trigger the wizard")
                await cog.mutedrolesetup(ctx)

            try:
                if muted_role in member.roles or await conn.fetchval(
                        "SELECT userID FROM mutes WHERE userID = $1 AND guildID = $2", member.id,
                        ctx.guild.id) == member.id:
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
    async def unmute(self, ctx, member: discord.Member):
        modandbotprotection = await checks.modAndBotProtection(self.bot, ctx, member, "unmute")
        if modandbotprotection is not None:
            await ctx.send(modandbotprotection)
            return

        async with self.bot.db.acquire() as conn:
            mutedroleid = (await conn.fetchrow("SELECT mutedRole FROM roles WHERE guildID = $1", ctx.guild.id))[0]
            if mutedroleid is None:
                cog = self.bot.get_cog('Setup')
                if not cog:
                    return await ctx.send(
                        "Set up cog not loaded and muted role not set, please manually set the muted role or load the setup cog to trigger the wizard")
                await cog.mutedrolesetup(ctx)

            muted_role = ctx.guild.get_role(mutedroleid)
            if muted_role is None:
                cog = self.bot.get_cog('Setup')
                if not cog:
                    return await ctx.send(
                        "Set up cog not loaded and muted role not set, please manually set the muted role or load the setup cog to trigger the wizard")
                await cog.mutedrolesetup(ctx)

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

            await self.bot.discordLogger.modlogs(ctx, 'unmute', member, ctx.author)

            await ctx.send(f"{member} has been unmuted.")

    # lockdown commands
    @checks.is_staff_or_perms("Mod", manage_channels=True)
    @flags.add_flag("--channel", "-c", type=discord.TextChannel, default=None)
    @flags.add_flag("--reason", '-r', type=str, default="", nargs="+")
    @flags.command(aliases=['lock'], )
    async def lockdown(self, ctx, **flag_args):
        """Locks a channel, flags can be in any order. -c flag is only needed if locking a channel *other than the one the command is ran in*"""
        staffRoles = await common.getStaffRoles(ctx)
        channel = flag_args['channel']
        if channel is None:
            channel = ctx.channel
        elif channel.id != ctx.channel.id:
            await ctx.send(f"{self.bot.discordLogger.emotes['lock']} {channel.mention} has been locked.")

        # set staff roles and bot perms in place
        for role in staffRoles:
            if channel.overwrites_for(role).send_messages is False:
                await channel.set_permissions(role, send_messages=True)
        await channel.set_permissions(ctx.me, send_messages=True)

        # iterate through all applied perms and set them accordingly
        errorString = ""
        for overwrite, permoverwriteobj in channel.overwrites.items():
            if isinstance(overwrite, discord.Role):
                if overwrite not in staffRoles:
                    try:
                        permoverwriteobj.send_messages = False
                        permoverwriteobj.add_reactions = False
                        await channel.set_permissions(overwrite, overwrite=permoverwriteobj)
                    except discord.Forbidden:
                        if not errorString:
                            errorString = "I was unable to lock all the permissions in this channel!"
                        continue
            elif isinstance(overwrite, discord.Member):
                if channel.overwrites_for(overwrite).send_messages and channel.permissions_for(
                        overwrite).manage_channels is False and overwrite != ctx.me:
                    permoverwriteobj.send_messages = False
                    permoverwriteobj.add_reactions = False
                    await channel.set_permissions(overwrite, overwrite=permoverwriteobj)
                    if not errorString:
                        errorString = "I was unable to lock all the permissions in this channel!"

        try:
            chanmsg = f"{self.bot.discordLogger.emotes['lock']} Channel locked."
            reason = None
            if flag_args['reason']:
                reason = ' '.join(flag_args['reason'])
            if reason:
                chanmsg += f" The reason is `{reason}`"
            if errorString:
                chanmsg += f" But, {errorString}"
            await channel.send(chanmsg)
            await self.bot.discordLogger.modlogs(ctx, "lock", channel, ctx.author, reason)

        except discord.Forbidden:
            await ctx.send("I don't have permission to lock channels!")

    @checks.is_staff_or_perms("Mod", manage_channels=True)
    @flags.add_flag("--channel", '-c', type=discord.TextChannel, default=None)
    @flags.command(aliases=['unlock'], )
    async def unlockdown(self, ctx, **flag_args):
        """Unlocks a channel, -c flag is not needed for unlocking the channel the command is invoked in"""

        staffRoles = await common.getStaffRoles(ctx)
        channel = flag_args['channel']
        if channel is None:
            channel = ctx.channel
        else:
            await ctx.send(f"{self.bot.discordLogger.emotes['unlock']} {channel.mention} has been unlocked.")

        # set staff roles and bot perms in place
        for role in staffRoles:
            if channel.overwrites_for(role).send_messages is False:
                await channel.set_permissions(role, send_messages=None)
        await channel.set_permissions(ctx.me, send_messages=None)

        # iterate through all applied perms and set them accordingly
        errorString = ""
        for overwrite, permoverwriteobj in channel.overwrites.items():
            if isinstance(overwrite, discord.Role):
                if overwrite not in staffRoles and overwrite.id != await self.bot.db.fetchval(
                        "SELECT mutedrole FROM roles WHERE guildid = $1", ctx.guild.id):
                    try:
                        permoverwriteobj.send_messages = None
                        permoverwriteobj.add_reactions = None
                        await channel.set_permissions(overwrite, overwrite=permoverwriteobj)
                    except discord.Forbidden:
                        if not errorString:
                            errorString = "I was unable to unlock all the permissions in this channel!"
                        continue
            elif isinstance(overwrite, discord.Member):
                if channel.overwrites_for(overwrite).send_messages and channel.permissions_for(
                        overwrite).manage_channels is False and overwrite != ctx.me:
                    permoverwriteobj.send_messages = False
                    permoverwriteobj.add_reactions = False
                    await channel.set_permissions(overwrite, overwrite=permoverwriteobj)
                    if not errorString:
                        errorString = "I was unable to unlock all the permissions in this channel!"

        try:
            chanmsg = f"{self.bot.discordLogger.emotes['unlock']} Channel unlocked."
            if errorString:
                chanmsg += f" But, {errorString}"
            await channel.send(chanmsg)
            await self.bot.discordLogger.modlogs(ctx, "unlock", channel, ctx.author)

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
    async def slowmode(self, ctx, channel: discord.TextChannel, slowtime, *, reason=None):
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
