import discord
import yaml
from discord.ext import commands
from utils import checks, errors, common
import typing
import logzero
from logzero import logger as consolelogger

logzero.logfile("logs/setupcog.log", maxBytes=1e6)


class Setup(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    async def getdbasset(self, asset: str, guild: discord.Guild):
        async with self.bot.db.acquire() as conn:
            if asset in ('modrole', 'adminrole', 'ownerrole', 'approvedrole', 'mutedrole'):
                return (await conn.fetchrow(f"SELECT {asset} FROM roles WHERE guildid = $1", guild.id))[0]

            elif asset in ('modlogs', 'messagelogs', 'memberlogs', 'auditlogs'):
                return (await conn.fetchrow(f"SELECT {asset} FROM log_channels WHERE guildid = $1", guild.id))[0]

            else:
                consolelogger.error("Invalid input given for asset")
                return None

    async def setunsetrole(self, ctx, role: discord.Role, roletype, mode):
        if not isinstance(role, discord.Role) and role is not None:
            await ctx.send("Invalid role given! Does this role exist?")
            return

        if roletype not in ('modrole', 'adminrole', 'ownerrole', 'approvedrole', 'mutedrole'):
            raise commands.BadArgument("Invalid Database Role")

        async with self.bot.db.acquire() as conn:

            if mode == 'unset':
                roleid = await self.getdbasset(roletype, ctx.guild)
                if roleid is None:
                    await ctx.send(f"No {roletype} to unset!")
                    return
                try:
                    await self.bot.discordLogger.logsetup("unset", f"{roletype} role", ctx.author,
                                                          ctx.guild.get_role(roleid), 'modlogs')
                except errors.loggingError:
                    consolelogger.warning(f"Failed to log {roletype} database unset on server {ctx.guild.name}.")
                await conn.execute(f"UPDATE roles SET {roletype} = NULL WHERE guildid = $1", ctx.guild.id)
                await ctx.send(f"{roletype} role unset!".title())

            else:
                # just in case!
                if role is None:
                    await ctx.send("Please enter a role to set")
                    return

                await conn.execute(f"UPDATE roles SET {roletype} = $1 WHERE guildid = $2", role.id, ctx.guild.id)
                await ctx.send(f"{roletype} role set!".title())
                try:
                    await self.bot.discordLogger.logsetup("set", f"{roletype} role", ctx.author,
                                                          await self.getdbasset(roletype,
                                                                                ctx.guild) if role is None else ctx.guild.get_role(
                                                              role.id), 'modlogs')
                except errors.loggingError:
                    consolelogger.warning(f"Failed to log {roletype} database set! on server {ctx.guild.name}")

    async def setunsetchannels(self, ctx, channel: typing.Union[discord.TextChannel, None], channeltype, mode):
        if not isinstance(channel, discord.TextChannel) and channel is not None:
            await ctx.send("Invalid channel, does this channel exist?")
            return

        if channeltype not in ('modlogs', 'messagelogs', 'memberlogs', 'auditlogs'):
            raise commands.BadArgument("Invalid Database Channel")

        async with self.bot.db.acquire() as conn:
            if mode == 'unset':
                try:
                    channelid = await self.getdbasset(channeltype, ctx.guild)
                    if channelid is None:
                        await ctx.send(f"No {channeltype} channel to unset!")
                        return

                    await self.bot.discordLogger.logsetup("unset", f"{channeltype} channel", ctx.author,
                                                          self.bot.get_channel(channelid), channeltype)

                except errors.loggingError:
                    consolelogger.warning(f"Failed log setting the {channel} log channel on server: {ctx.guild.name}")

                await conn.execute(f"UPDATE log_channels SET {channeltype} = NULL WHERE guildid = $1", ctx.guild.id)
                await ctx.send(f"{channeltype} channel unset!".title())

            else:
                # just in case
                if channel is None:
                    await ctx.send("Please enter a channel to set")
                    return

                await conn.execute(f"UPDATE log_channels SET {channeltype} = $1 WHERE guildid = $2", channel.id,
                                   ctx.guild.id)
                await ctx.send(f"{channeltype} channel set!".title())

                try:
                    await self.bot.discordLogger.logsetup("set", f"{channeltype} channel", ctx.author,
                                                          channel, channeltype)
                except errors.loggingError:
                    consolelogger.warning(f"Failed log setting the {channel} log channel on server: {ctx.guild.name}")

    # channels

    @checks.is_staff_or_perms("Owner", administrator=True)
    @commands.group(invoke_without_command=True)
    async def logchannel(self, ctx):
        """"To add a logchannel to the database (and to enable logging) please use [p]logchannel <set|unset> <type of log you wish to set> <channel>. valid channel options are: `modlogs`, `memberlogs`, `messagelogs` """
        await ctx.send_help(ctx.command)

    @checks.is_staff_or_perms("Owner", administrator=True)
    @logchannel.command(aliases=['set'])
    async def channelset(self, ctx, channeltype, channel: discord.TextChannel):
        if channeltype.lower() not in ('modlogs', 'messagelogs', 'memberlogs', 'auditlogs'):
            await ctx.send("Invalid log type. valid options are: `modlogs`, `messagelogs`, `memberlogs`")
        else:
            await self.setunsetchannels(ctx, channel, channeltype, 'set')

    @checks.is_staff_or_perms("Owner", administrator=True)
    @logchannel.command(aliases=['unset'])
    async def channelunset(self, ctx, channeltype):
        if channeltype.lower() not in ('modlogs', 'messagelogs', 'memberlogs', 'auditlogs'):
            await ctx.send("Invalid log type. valid options are: `modlogs`, `messagelogs`, `memberlogs`")
        else:
            await self.setunsetchannels(ctx, None, channeltype, 'unset')

    # roles

    @checks.is_staff_or_perms("Owner", administrator=True)
    @commands.group(invoke_without_command=True, aliases=['serverrole'])
    async def dbrole(self, ctx):
        """To set or unset a role to the database as a staff role, please use [p]dbrole <set|unset> <type of staff role> <role>. valid options are: `adminrole`, `approvedrole`, `modrole`, `mutedrole`, `ownerrole`"""
        await ctx.send_help(ctx.command)


    @checks.is_staff_or_perms("Owner", administrator=True)
    @dbrole.command(aliases=['set'])
    async def roleset(self, ctx, roletype, role: discord.Role):
        if roletype.lower() not in ('adminrole', 'approvedrole', 'modrole', 'mutedrole', 'ownerrole'):
            await ctx.send(
                "Invalid role type, valid role options are: `adminrole`, `approvedrole`, `modrole`, `mutedrole`, `ownerrole`")
        else:
            await self.setunsetrole(ctx, role, roletype, 'set')

    @checks.is_staff_or_perms("Owner", administrator=True)
    @dbrole.command(aliases=['unset'])
    async def roleunset(self, ctx, roletype):
        if roletype.lower() not in ('adminrole', 'approvedrole', 'modrole', 'mutedrole', 'ownerrole'):
            await ctx.send(
                "Invalid role type, valid role options are: `adminrole`, `approvedrole`, `modrole`, `mutedrole`, `ownerrole`")
        else:
            await self.setunsetrole(ctx, None, roletype, 'unset')

    @checks.is_staff_or_perms("Owner", administrator=True)
    @commands.guild_only()
    @commands.command()
    async def togglejoinlogs(self, ctx):
        async with self.bot.db.acquire() as conn:
            memberlogschannelid = await conn.fetchval("SELECT memberlogs FROM log_channels WHERE guildid =  $1",
                                                      ctx.guild.id)
            if memberlogschannelid is None:
                await ctx.send("Member log channel not configured!")
                return

            if await conn.fetchval("SELECT enablejoinleavelogs FROM guild_settings WHERE guildid = $1", ctx.guild.id):
                await conn.execute("UPDATE guild_settings SET enablejoinleavelogs = FALSE WHERE guildid = $1",
                                   ctx.guild.id)
                await ctx.send("Join and leave logs are now off!")
                await self.bot.discordLogger.togglelogsetup("unset", "join leave logs", ctx.author, 'memberlogs')
            else:
                await conn.execute("UPDATE guild_settings SET enablejoinleavelogs = TRUE WHERE guildid = $1",
                                   ctx.guild.id)
                await ctx.send("Join and leave logs are now on!")
                await self.bot.discordLogger.togglelogsetup("set", "join leave logs", ctx.author, 'memberlogs')

    @checks.is_staff_or_perms("Owner", administrator=True)
    @commands.guild_only()
    @commands.command()
    async def togglecoremessagelogs(self, ctx):
        async with self.bot.db.acquire() as conn:
            memberlogschannelid = await conn.fetchval("SELECT messagelogs FROM log_channels WHERE guildid =  $1",
                                                      ctx.guild.id)
            if memberlogschannelid is None:
                await ctx.send("Message log channel not configured!")
                return

            if await conn.fetchval("SELECT enableCoreMessageLogs FROM guild_settings WHERE guildid = $1", ctx.guild.id):
                await conn.execute("UPDATE guild_settings SET enableCoreMessageLogs = FALSE WHERE guildid = $1",
                                   ctx.guild.id)
                await ctx.send("Message edits and deletes are no longer logged!")
                await self.bot.discordLogger.togglelogsetup("unset", "core message logs", ctx.author, 'messagelogs')
            else:
                await conn.execute("UPDATE guild_settings SET enableCoreMessageLogs = TRUE WHERE guildid = $1",
                                   ctx.guild.id)
                await ctx.send("Message edits and deletes are now being logged!")
                await self.bot.discordLogger.togglelogsetup("set", "core message logs", ctx.author, 'messagelogs')

    @commands.guild_only()
    @commands.group(invoke_without_command=True)
    async def prefix(self, ctx):
        """Manage and list the guild's custom prefixes, by default the only avalable prefixes will be mentioning the bot or the global default prefix"""
        await ctx.send_help(ctx.command)

    @checks.is_staff_or_perms("Admin", manage_server=True)
    @prefix.command()
    async def add(self, ctx, newprefix):
        """Adds a prefix to the bot for your guild (Admin+, or manage server) (No more than 10 per guild)"""
        newprefix = discord.utils.escape_mentions(newprefix)  # ha ha no
        async with self.bot.db.acquire() as conn:
            guildprefixes = await conn.fetchval("SELECT prefixes FROM guild_settings WHERE guildid = $1", ctx.guild.id)
            if guildprefixes is None:
                guildprefixes = []

            if newprefix not in guildprefixes and len(guildprefixes) < 10:
                await conn.execute("UPDATE guild_settings SET prefixes = array_append(prefixes, $1) WHERE guildid = $2",
                                   newprefix, ctx.guild.id)
                return await ctx.send(f"Added prefix `{newprefix}` as a guild prefix")
            else:
                if len(guildprefixes) < 10:
                    return await ctx.send("No more than 10 custom prefixes may be added!")
                else:
                    return await ctx.send("This prefix is already in the guild!")

    @checks.is_staff_or_perms("Admin", manage_server=True)
    @prefix.command(aliases=['del', 'delete'])
    async def remove(self, ctx, prefix):
        """Removes a prefix from the guild (Admin+, or manage_server)"""
        async with self.bot.db.acquire() as conn:
            guildprefixes = await conn.fetchval("SELECT prefixes FROM guild_settings WHERE guildid = $1", ctx.guild.id)
            if not guildprefixes:
                return await ctx.send("No custom guild prefixes saved!")
            elif prefix not in guildprefixes:
                return await ctx.send("This prefix is not saved to this guild!")
            else:
                await conn.execute("UPDATE guild_settings SET prefixes = array_remove(prefixes, $1) WHERE guildid = $2", prefix, ctx.guild.id)
                await ctx.send("Prefix removed!")

    @prefix.command()
    async def list(self, ctx):
        """List the guild's custom prefixes"""
        guildprefixes = await self.bot.db.fetchval("SELECT prefixes FROM guild_settings WHERE guildid = $1", ctx.guild.id)
        embed = discord.Embed(title=f"Prefixes for {ctx.guild.name}", color=common.gen_color(ctx.guild.id))
        if guildprefixes:
            prefixstr = ""
            for prefix in guildprefixes:
                prefixstr += f"- `{prefix}`\n"
            embed.set_footer(text=f"{len(guildprefixes)} custom guild prefixes saved" if len(guildprefixes) != 1 else "1 custom guild prefix saved")

        else:
            prefixstr = "No prefixes saved"

        embed.description = prefixstr
        embed.add_field(name="Global default prefixes", value=f"- {ctx.me.mention}\n- `{self.bot.readConfig('default_prefix')}`", inline=False)
        await ctx.send(embed=embed)


    @checks.is_bot_owner()
    @commands.command()
    async def switchdefaultprefix(self, ctx, prefix):
        prefix = discord.utils.escape_mentions(prefix)
        with open('config.yml', 'r+') as f:
            config = yaml.safe_load(f)
            config['default_prefix'] = prefix
            yaml.dump(config, f)
        await ctx.send("Changed default global prefix")



def setup(bot):
    bot.add_cog(Setup(bot))
