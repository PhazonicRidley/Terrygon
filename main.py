#!/usr/bin/env python3.8
from traceback import format_exception
from os.path import dirname, realpath
from os import chdir
import sys
import discord
import yaml
from discord.ext import commands
import asyncpg
import asyncio
from logzero import setup_logger
from utils import logger as discordLogger, errors
import json

# set file logger up
consoleLogger = setup_logger(name='mainlogs', logfile='logs/main.log', maxBytes=100000)
errorlogs = setup_logger(name='errors', logfile='logs/errors.log', maxBytes=100000)
# Change to script's directory
path = dirname(realpath(__file__))
chdir(path)


# modified from https://gitlab.com/lightning-bot/Lightning/-/blob/v3/lightning.py#L42 and https://github.com/Rapptz/RoboDanny/blob/rewrite/bot.py#L44
async def _callable_prefix(bot, message):
    default_prefix = bot.readConfig('default_prefix')
    guildprefixes = await bot.db.fetchval("SELECT prefixes FROM guild_settings WHERE guildid = $1", message.guild.id)
    if guildprefixes:
        guildprefixes.append(default_prefix)
        return commands.when_mentioned_or(*guildprefixes)(bot, message)
    else:
        return commands.when_mentioned_or(default_prefix)(bot, message)

class Terrygon(commands.Bot):
    def __init__(self):
        loop = asyncio.get_event_loop()
        help_cmd = commands.MinimalHelpCommand(dm_help=None, dm_help_threshold=800)
        super().__init__(command_prefix=_callable_prefix, description=self.readConfig("description"),
                         max_messages=10000, help_command=help_cmd)

        self.db = loop.run_until_complete(self.create_pool(self.readConfig('db')))
        consoleLogger.info("Database pool has started!")
        self.discordLogger = discordLogger.Logger(self)
        consoleLogger.info("Discord Logger has been configured")

    # open config
    def readConfig(self, config) -> str:
        try:
            with open("config.yml", "r") as f:
                loadedYml = yaml.safe_load(f)
                return loadedYml[config]
        except FileNotFoundError:
            print("Cannot find config.yml. Does it exist?")
            consoleLogger.errors("Failed to read config.yml")
            sys.exit(1)

    # adapted from lightning https://gitlab.com/lightning-bot/Lightning/-/blob/v3/lightning.py
    async def create_pool(self, dbPath):
        async def configureconnectioncodec(conn):
            await conn.set_type_codec('jsonb', encoder=json.dumps, decoder=json.loads, schema='pg_catalog')

        return await asyncpg.create_pool(self.readConfig("db"), init=configureconnectioncodec)

    async def preparedb(self):
        """Prepare our database for use"""
        async with self.db.acquire() as conn:
            try:
                with open("schema.sql", 'r') as schema:
                    try:
                        await conn.execute(schema.read())
                    except asyncpg.PostgresError as e:
                        consoleLogger.exception(
                            "A SQL error has occurred while running the schema, traceback is:\n{}".format("".join(
                                format_exception(type(e), e, e.__traceback__))))
                        raise errors.sqlError("preparedb", format_exception(type(e), e, e.__traceback__))
            except FileNotFoundError:
                print(
                    "schema file not found, please check your files, remember to rename schema.sql.example to schema.sql when you would like to use it")
                await self.logout()

    async def on_command_error(self, ctx, error):
        if isinstance(error, (commands.errors.CommandNotFound, commands.errors.CheckFailure)):
            return

        elif isinstance(error, commands.CommandInvokeError) and isinstance(error.original, discord.HTTPException):
            await ctx.send(
                f"An HTTP {error.original.status} has occurred for the following reason: `{error.original.text}`")

        elif isinstance(error, (
        commands.MissingRequiredArgument, commands.BadArgument, commands.BadUnionArgument, commands.TooManyArguments)):
            await ctx.send_help(ctx.command)

        elif isinstance(error, commands.errors.CommandOnCooldown):
            await ctx.send("\
            {} This command was used {:.2f}s ago and is on cooldown.\
             Try again in {:.2f}s.".format(ctx.message.author.mention, error.cooldown.per - error.retry_after,
                                           error.retry_after))

        elif isinstance(error, commands.errors.NoPrivateMessage):
            await ctx.send("You cannot use this command outside of a server!")

        elif isinstance(error, errors.missingStaffRoleOrPerms):
            msg = f"You do not have at least the {error.modrole} role"
            if error.perms:
                msg += " or the following permissions: "
                for perm in error.perms:
                    msg += f"`{perm}` "
            msg += " and thus cannot use this command."
            await ctx.send(msg)

        elif isinstance(error, errors.noStaffRolesSaved):
            await ctx.send("No staff roles in the database for this server please add some!")

        elif isinstance(error, errors.botOwnerError):
            await ctx.send("You cannot use this as you are not a bot owner")

        elif isinstance(error, errors.untrustedError):
            await ctx.send("You are not a trusted user or a staff member and thus cannot use this!")

        else:
            await ctx.send(f"An error occurred while processing the `{ctx.command.name}` command.")
            print('Ignoring exception in command {0.command} in {0.message.channel}'.format(ctx))
            logMsg = "Exception occurred in `{0.command}` in {0.message.channel.mention}".format(ctx)
            tb = format_exception(type(error), error, error.__traceback__)
            print(''.join(tb))
            # TODO redo error logging in separate files
            errorlogs.info(f"COMMAND: {ctx.command.name}, GUILD: {ctx.guild.name} CHANNEL: {ctx.channel.name}")
            errorlogs.exception(logMsg + "".join(tb) + '\n\n')
            for errorchanid in self.readConfig('boterrchannelid'):
                errchan = self.get_channel(errorchanid)
                if errchan:
                    await errchan.send(logMsg + "\n```" + ''.join(tb) + "\n```")
                else:
                    consoleLogger.info("No error channel set!")

    async def isLogRegistered(self, guild: discord.Guild, logtype):
        async with self.db.acquire() as conn:
            logChannelTypes = (await conn.fetch(
                "SELECT column_name FROM information_schema.columns WHERE table_name = 'log_channels' AND column_name != 'guildid';"))[
                0]
            i = 0
            for channel in logChannelTypes:
                if logtype == channel:
                    break
                i += 1

            if i > len(logChannelTypes):
                return

            if (await conn.fetchrow(f"SELECT {logtype} FROM log_channels WHERE guildid = $1", guild.id)) is not None:
                return True
            else:
                return False

    async def on_ready(self):
        await self.preparedb()
        self.load_extension("jishaku")
        consoleLogger.info("jsk has been loaded")
        consoleLogger.info("Schema configured")
        if self.readConfig("addons") is not None:
            for addon in self.readConfig("addons"):
                try:
                    self.load_extension("addons." + addon)
                    consoleLogger.info(f"{addon} addon loaded")
                except Exception as e:
                    errmsg = "Failed to load {}:\n{}".format(addon,
                                                             "".join(format_exception(type(e), e, e.__traceback__)))
                    consoleLogger.exception(errmsg)

        # Notify user if a cog fails to load.
        if self.readConfig("cogs") is not None:
            for cog in self.readConfig("cogs"):
                try:
                    self.load_extension("cogs." + cog)
                    consoleLogger.info(f"{cog} cog loaded")

                except Exception as e:
                    errmsg = "Failed to load {}:\n{}".format(cog,
                                                             "".join(format_exception(type(e), e, e.__traceback__)))
                    consoleLogger.exception(errmsg)

        loginMsg = f"Client logged in as {self.user.name}"
        consoleLogger.info(f"LOGIN: {loginMsg}")
        await self.change_presence(activity=discord.Game(self.readConfig("activity")))


if __name__ == "__main__":
    bot = Terrygon()
    bot.run(bot.readConfig("token"))
