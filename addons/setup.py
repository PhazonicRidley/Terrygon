import discord
import yaml
from discord.ext import commands, flags
from utils import checks, errors, common, paginator
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
                    return -1
                try:
                    role = ctx.guild.get_role(roleid)
                    if not role:
                        raise errors.loggingError("Deleted role", ctx.guild)
                    await self.bot.discordLogger.logsetup("unset", f"{roletype} role", ctx.author,
                                                          role, 'modlogs')
                except errors.loggingError:
                    consolelogger.warning(f"Failed to log {roletype} database unset on server {ctx.guild.name}.")
                await conn.execute(f"UPDATE roles SET {roletype} = NULL WHERE guildid = $1", ctx.guild.id)
                return 0

            else:
                # just in case!
                if role is None:
                    return -1

                await conn.execute(f"UPDATE roles SET {roletype} = $1 WHERE guildid = $2", role.id, ctx.guild.id)
                try:
                    await self.bot.discordLogger.logsetup("set", f"{roletype} role", ctx.author,
                                                          await self.getdbasset(roletype,
                                                                                ctx.guild) if role is None else ctx.guild.get_role(
                                                              role.id), 'modlogs')
                except errors.loggingError:
                    consolelogger.warning(f"Failed to log {roletype} database set! on server {ctx.guild.name}")

                return 0

    async def setunsetchannels(self, ctx, channel: typing.Union[discord.TextChannel, None], channeltype, mode):
        """Sets a log channel to the database, mode should be either `set` or `unset`"""
        if not isinstance(channel, discord.TextChannel) and channel is not None:
            await ctx.send("Invalid channel, does this channel exist?")
            return

        if channeltype not in ('modlogs', 'messagelogs', 'memberlogs', 'auditlogs'):
            raise commands.BadArgument("Invalid Database Channel")

        async with self.bot.db.acquire() as conn:
            if mode.lower() == 'unset':
                try:
                    channelid = await self.getdbasset(channeltype, ctx.guild)
                    if channelid is None:
                        return -1

                    await self.bot.discordLogger.logsetup("unset", f"{channeltype} channel", ctx.author,
                                                          self.bot.get_channel(channelid), channeltype)

                except errors.loggingError:
                    consolelogger.warning(f"Failed log setting the {channel} log channel on server: {ctx.guild.name}")

                await conn.execute(f"UPDATE log_channels SET {channeltype} = NULL WHERE guildid = $1", ctx.guild.id)
                return 0

            elif mode.lower() == 'set':
                # just in case
                if channel is None:
                    await ctx.send("Please enter a channel to set")
                    return -1

                await conn.execute(f"UPDATE log_channels SET {channeltype} = $1 WHERE guildid = $2", channel.id,
                                   ctx.guild.id)

                try:
                    await self.bot.discordLogger.logsetup("set", f"{channeltype} channel", ctx.author, channel,
                                                          channeltype)
                except errors.loggingError:
                    consolelogger.warning(f"Failed log setting the {channel} log channel on server: {ctx.guild.name}")

                return 0

            else:
                raise commands.BadArgument("Unknown mode, valid modes are set and unset!")

    # channels

    @checks.is_staff_or_perms("Owner", administrator=True)
    @commands.group(invoke_without_command=True)
    async def logchannel(self, ctx):
        """"To add a logchannel to the database (and to enable logging) please use [p]logchannel <set|unset> <type of log you wish to set> <channel>. valid channel options are: `modlogs`, `memberlogs`, `messagelogs` """
        await ctx.send_help(ctx.command)

    @checks.is_staff_or_perms("Owner", administrator=True)
    @flags.add_flag("--modlogs", type=discord.TextChannel)
    @flags.add_flag("--memberlogs", type=discord.TextChannel)
    @flags.add_flag("--messagelogs", type=discord.TextChannel)
    @logchannel.command(cls=flags.FlagCommand, aliases=['set'])
    async def channelset(self, ctx, **logchannels):
        """Sets a channel to be used as a log channel
        - `--modlogs` logs moderaton commands like warn/ban/mute/kick/lockdown
        - `--memberlogs` logs all data relating to users being updated, like nickname changes or role changes
        - `--messagelogs` logs all data relating to messages, such as edits, deletions, or pinned messages by trusted members
        """
        activeFlags = {l for l in logchannels.items() if l[1]}
        if not activeFlags:
            return await ctx.send(
                "Please specify a logchannel type you would like to add, flags are `--modlogs`, `--memberlogs`, and `--messagelogs`")

        else:
            msg = ""
            async with ctx.channel.typing():
                for chantype, channel in activeFlags:
                    if await self.setunsetchannels(ctx, channel, chantype, 'set') == 0:
                        msg += f"{chantype.title()}, "

            if msg:
                await ctx.send(msg.rstrip(", ") + " have been set!")
            else:
                # should never appear
                await ctx.send("Unable to set any channels to the database!")

    @checks.is_staff_or_perms("Owner", administrator=True)
    @flags.add_flag("--modlogs", default=None, action="store_true")
    @flags.add_flag("--memberlogs", default=None, action="store_true")
    @flags.add_flag("--messagelogs", default=None, action="store_true")
    @logchannel.command(cls=flags.FlagCommand, aliases=['unset'])
    async def channelunset(self, ctx, **channeltype):
        activeFlags = [l[0] for l in channeltype.items() if l[1]]
        if not activeFlags:
            await ctx.send(
                "Please specify a logchannel type you would like to remove, flags are `--modlogs`, `--memberlogs`, and `--messagelogs`")
        else:
            msg = ""
            async with ctx.channel.typing():
                for logtype in activeFlags:
                    if await self.setunsetchannels(ctx, None, logtype, 'unset') == 0:
                        msg += f"{logtype.title()}, "

            if msg:
                await ctx.send(msg.rstrip(", ") + " have been unset!")
            else:
                # should never appear
                await ctx.send("Unable to unset any channels to the database!")

    # roles

    @checks.is_staff_or_perms("Owner", administrator=True)
    @commands.group(invoke_without_command=True, aliases=['serverrole', 'dbrole'])
    async def staffrole(self, ctx):
        """To set or unset a role to the database as a staff role, please use [p]dbrole <set|unset> <type of staff role> <role>. valid options are: `adminrole`, `approvedrole`, `modrole`, `mutedrole`, `ownerrole`"""
        await ctx.send_help(ctx.command)

    @checks.is_staff_or_perms("Owner", administrator=True)
    @flags.add_flag("--adminrole", type=discord.Role)
    @flags.add_flag("--modrole", type=discord.Role)
    @flags.add_flag("--ownerrole", type=discord.Role)
    @staffrole.command(cls=flags.FlagCommand, aliases=['set'])
    async def roleset(self, ctx, **role_flags):
        """Sets a staff role to be used in the database

        - `--adminrole` Role for administrators.
        - `--ownerrole` Role for owners.
        - `--modrole` Role for moderators
        """
        activeFlags = {l for l in role_flags.items() if l[1]}
        if not activeFlags:
            return await ctx.send(
                "Please specify a database role you would like to add, flags are `--adminrole`, `--modrole`, and `--ownerrole`")
        else:
            msg = ""
            async with ctx.channel.typing():
                for roletype, role in activeFlags:
                    if await self.setunsetrole(ctx, role, roletype, 'set') == 0:
                        msg += f"{roletype.title()}, "

            if msg:
                await ctx.send(msg.rstrip(", ") + " have been set!")
            else:
                await ctx.send("Unable to set any roles to the database!")

    @checks.is_staff_or_perms("Owner", administrator=True)
    @flags.add_flag("--adminrole", default=None, action="store_true")
    @flags.add_flag("--modrole", default=None, action="store_true")
    @flags.add_flag("--ownerrole", default=None, action="store_true")
    @staffrole.command(cls=flags.FlagCommand, aliases=['unset'])
    async def roleunset(self, ctx, **role_flags):
        activeFlags = {l for l in role_flags.items() if l[1]}
        if not activeFlags:
            return await ctx.send(
                "Please specify a database role you would like to add, flags are `--adminrole`, `--modrole`, and `--ownerrole`")
        else:
            msg = ""
            async with ctx.channel.typing():
                for roletype, role in activeFlags:
                    if await self.setunsetrole(ctx, None, roletype, 'unset') == 0:
                        msg += f"{roletype.title()}, "

            if msg:
                await ctx.send(msg.rstrip(", ") + " have been unset!")
            else:
                # should never appear
                await ctx.send("Unable to unset any roles to the database!")

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
    @checks.is_staff_or_perms('Owner', administrator=True)
    @commands.group(invoke_without_command=True)
    async def logs(self, ctx):
        """Command used to manage all logging systems. You can set and unset channels, modroles, and toggle which things you would like to log for your server"""
        await ctx.send_help(ctx.command)

    @commands.guild_only()
    @checks.is_staff_or_perms('Owner', administrator=True)
    @logs.command()
    async def joinleave(self, ctx):
        """Enables or disables joining and leaving logs"""
        await self.togglejoinlogs(ctx)

    @commands.guild_only()
    @checks.is_staff_or_perms('Owner', administrator=True)
    @logs.command()
    async def editsdeletes(self, ctx):
        """Enables or disables message edits or deletions"""
        await self.togglecoremessagelogs(ctx)

    @commands.guild_only()
    @checks.is_staff_or_perms('Mod', manage_roles=True)
    @commands.group(invoke_without_command=True)
    async def mutedrole(self, ctx):
        """Manage muted role"""
        await ctx.send_help(ctx.command)

    @commands.guild_only()
    @checks.is_staff_or_perms('Mod', manage_roles=True)
    @mutedrole.command(aliases=['set'])
    async def mutedroleset(self, ctx, role: discord.Role = None):
        out = await self.mutedrolesetup(ctx, role)
        if out:
            await ctx.send(out)

    @commands.guild_only()
    @checks.is_staff_or_perms('Admin', manage_guild=True)
    @mutedrole.command(aliases=['unset'])
    async def mutedroleunset(self, ctx):
        """Unset's the muted role (Admin+, manage server)"""
        mutedroleid = await self.bot.db.fetchval("SELECT mutedrole FROM roles WHERE guildid = $1", ctx.guild.id)
        if not mutedroleid:
            return await ctx.send("No mutedrole saved in the database.")
        await self.setunsetrole(ctx, None, 'mutedrole', 'unset')
        res, msg = await paginator.YesNoMenu("Muted role, unset, would you like to delete it?").prompt(ctx)
        if res:
            try:
                await ctx.guild.get_role(mutedroleid).delete()
                await msg.edit(content="Role deleted!")
            except discord.Forbidden:
                return await msg.edit(content="I cannot delete roles!")
        else:
            await msg.edit(content="Role not deleted.")

    async def mutedrolesetup(self, ctx, role: discord.Role = None):
        if role is None:
            res, msg = await paginator.YesNoMenu("No muted role detected, would you like to create one?").prompt(ctx)
            if res:
                try:
                    role = await ctx.guild.create_role(name='Muted', reason="New role for muting members")
                except discord.Forbidden:
                    return "I am unable to create roles, please check permissions!"
                await msg.edit(
                    content="New role named `Muted` created, added to the database, and set up with all the channels")
            else:
                return await msg.edit(content="Canceled")
        else:
            await ctx.send("Muted role set!")

        # first go thru the categories
        try:
            for category in ctx.guild.categories:
                await category.set_permissions(role, send_messages=False, connect=False)

            # next the remaining channels
            for tc in ctx.guild.text_channels:
                if not tc.permissions_synced:
                    await tc.set_permissions(role, send_messages=False)

            for vc in ctx.guild.voice_channels:
                if not vc.permissions_synced:
                    await vc.set_permissions(role, connect=False)
            for member in ctx.guild.members:
                if member.id == await self.bot.db.fetchval("SELECT userid FROM mutes WHERE guildid = $1", ctx.guild.id):
                    await member.add_roles(role, reason="Carrying over mutes")
        except discord.Forbidden:
            return "Unable to set channel permissions, please check my permissions!"

        await self.setunsetrole(ctx, role, 'mutedrole', 'set')

    @commands.guild_only()
    @commands.group(invoke_without_command=True)
    async def prefix(self, ctx):
        """Manage and list the guild's custom prefixes, by default the only avalable prefixes will be mentioning the bot or the global default prefix"""
        await ctx.send_help(ctx.command)

    @checks.is_staff_or_perms("Admin", manage_guild=True)
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

    @checks.is_staff_or_perms("Admin", manage_guild=True)
    @prefix.command(aliases=['del', 'delete'])
    async def remove(self, ctx, prefix):
        """Removes a prefix from the guild (Admin+, or Manage Server)"""
        async with self.bot.db.acquire() as conn:
            guildprefixes = await conn.fetchval("SELECT prefixes FROM guild_settings WHERE guildid = $1", ctx.guild.id)
            if not guildprefixes:
                return await ctx.send("No custom guild prefixes saved!")
            elif prefix not in guildprefixes:
                return await ctx.send("This prefix is not saved to this guild!")
            else:
                await conn.execute("UPDATE guild_settings SET prefixes = array_remove(prefixes, $1) WHERE guildid = $2",
                                   prefix, ctx.guild.id)
                await ctx.send("Prefix removed!")

    @prefix.command()
    async def list(self, ctx):
        """List the guild's custom prefixes"""
        guildprefixes = await self.bot.db.fetchval("SELECT prefixes FROM guild_settings WHERE guildid = $1",
                                                   ctx.guild.id)
        embed = discord.Embed(title=f"Prefixes for {ctx.guild.name}", color=common.gen_color(ctx.guild.id))
        if guildprefixes:
            prefixstr = ""
            for prefix in guildprefixes:
                prefixstr += f"- `{prefix}`\n"
            embed.set_footer(text=f"{len(guildprefixes)} custom guild prefixes saved" if len(
                guildprefixes) != 1 else "1 custom guild prefix saved")

        else:
            prefixstr = "No prefixes saved"

        embed.description = prefixstr
        embed.add_field(name="Global default prefixes",
                        value=f"- {ctx.me.mention}\n- `{self.bot.readConfig('default_prefix')}`", inline=False)
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
