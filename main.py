#!/usr/bin/env python3.8
from traceback import format_exception
from os.path import dirname, realpath
from os import chdir
import sys
import discord
import yaml
from discord.ext import commands, flags
import asyncpg
import asyncio
from logzero import setup_logger
from utils import logger as discord_logger, errors, scheduler
import json

# set file logger up
console_logger = setup_logger(name='mainlogs', logfile='logs/main.log', maxBytes=100000)
error_logs = setup_logger(name='errors', logfile='logs/errors.log', maxBytes=100000)
# Change to script's directory
path = dirname(realpath(__file__))
chdir(path)


# modified from https://gitlab.com/lightning-bot/Lightning/-/blob/v3/lightning.py#L42 and https://github.com/Rapptz/RoboDanny/blob/rewrite/bot.py#L44
async def _callable_prefix(bot, message):
    default_prefix = read_config('default_prefix')
    if message.guild is None:
        return commands.when_mentioned_or(default_prefix)(bot, message)
    guild_prefixes = await bot.db.fetchval("SELECT prefixes FROM guild_settings WHERE guildid = $1", message.guild.id)
    if guild_prefixes:
        guild_prefixes.append(default_prefix)
        return commands.when_mentioned_or(*guild_prefixes)(bot, message)
    else:
        return commands.when_mentioned_or(default_prefix)(bot, message)


def read_config(config) -> str:
    try:
        with open("config.yml", "r") as f:
            loadedYml = yaml.safe_load(f)
            return loadedYml[config]
    except FileNotFoundError:
        print("Cannot find config.yml. Does it exist?")
        console_logger.errors("Failed to read config.yml")
        sys.exit(1)


# adapted from lightning https://gitlab.com/lightning-bot/Lightning/-/blob/v3/lightning.py
async def create_pool():
    async def configure_connection_codec(conn):
        await conn.set_type_codec('jsonb', encoder=json.dumps, decoder=json.loads, schema='pg_catalog')

    return await asyncpg.create_pool(read_config("db"), init=configure_connection_codec)


class TerryHelp(commands.MinimalHelpCommand):
    """Custom:tm:"""

    def __init__(self, **options):
        super().__init__(**options)

    # taken from and slightly modified from https://github.com/Rapptz/discord.py/blob/master/discord/ext/commands/help.py#L971
    async def send_pages(self):
        destination = self.get_destination()
        if type(destination) == discord.Member:
            try:
                await self.context.message.add_reaction("\U0001f4ec")
            except discord.Forbidden:
                pass
        for page in self.paginator.pages:
            await destination.send(page)


class Terrygon(commands.Bot):
    def __init__(self):
        self.loop = asyncio.get_event_loop()
        help_cmd = TerryHelp(dm_help=None, dm_help_threshold=800)
        super().__init__(command_prefix=_callable_prefix, description=read_config("description"), max_messages=10000,
                         help_command=help_cmd,
                         allowed_mentions=discord.AllowedMentions(everyone=False, users=True, roles=True),
                         intents=discord.Intents().all())

        try:
            self.db = self.loop.run_until_complete(create_pool())
        except Exception:
            print("Unable to connect to the postgresql database, please check your configuration!")
            exit(1)
        console_logger.info("Database pool has started!")
        self.discord_logger = discord_logger.Logger(self)
        self.scheduler = scheduler.Scheduler(self)
        self.is_in_menu = False  # flag to check if we are in a menu
        console_logger.info("Discord Logger has been configured")

    async def prepare_db(self):
        """Prepare our database for use"""
        async with self.db.acquire() as conn:
            try:
                with open("schema.sql", 'r') as schema:
                    try:
                        await conn.execute(schema.read())
                    except asyncpg.PostgresError as e:
                        console_logger.exception(
                            "A SQL error has occurred while running the schema, traceback is:\n{}".format("".join(
                                format_exception(type(e), e, e.__traceback__))))
                        print(format_exception(type(e), e, e.__traceback__))
                        sys.exit(-1)

            except FileNotFoundError:
                print(
                    "schema file not found, please check your files, remember to rename schema.sql.example to schema.sql when you would like to use it")
                sys.exit(-1)

    async def on_command_error(self, ctx, error):
        # handles errors for commands that do not exist
        if isinstance(error, commands.errors.CommandNotFound):
            return

        # handles all uncaught http connection failures.
        elif isinstance(error, commands.CommandInvokeError) and isinstance(error.original, discord.HTTPException):
            await ctx.send(
                f"An HTTP {error.original.status} error has occurred for the following reason: `{error.original.text}`")

        # handles all bad command usage
        elif isinstance(error, (
                commands.MissingRequiredArgument, commands.BadArgument, commands.BadUnionArgument,
                commands.TooManyArguments,
                flags.ArgumentParsingError)):
            await ctx.send_help(ctx.command)

        # handles command cool downs
        elif isinstance(error, commands.errors.CommandOnCooldown):
            await ctx.send("This command was used {:.2f}s ago and is on cooldown. Try again in {:.2f}s.".format(
                error.cooldown.per - error.retry_after, error.retry_after))

        # handles commands that are attempted to be used outside a guild.
        elif isinstance(error, commands.errors.NoPrivateMessage):
            await ctx.send("You cannot use this command outside of a server!")

        # handles a privileged command when a user with out the right requirements attempts to use it.
        elif isinstance(error, errors.missingStaffRoleOrPerms):
            msg = f"You do not have at least the {error.modrole} role"
            if error.perms:
                msg += " or the following permissions: "
                for perm in error.perms:
                    msg += f"`{perm}` "
            msg += " and thus cannot use this command."
            await ctx.send(msg)

        # handles command that require staff roles and none are saved.
        elif isinstance(error, errors.noStaffRolesSaved):
            await ctx.send("No staff roles in the database for this server please add some!")

        # handles all bot owner commands that are used by someone who is not a bot owner.
        elif isinstance(error, (errors.botOwnerError, commands.errors.NotOwner)):
            await ctx.send("You cannot use this as you are not a bot owner")

        # handles trusted commands used by untrusted users.
        elif isinstance(error, errors.untrustedError):
            await ctx.send("You are not a trusted user or a staff member and thus cannot use this!")

        # handles any uncaught command, posts traceback in the assigned bot errors channel.
        else:
            await ctx.send(f"An error occurred while processing the `{ctx.command.name}` command.")
            print('Ignoring exception in command {0.command} in {0.message.channel}'.format(ctx))
            try:
                log_msg = "Exception occurred in `{0.command}` in {0.message.channel.mention}".format(ctx)
                error_logs.info(f"COMMAND: {ctx.command.name}, GUILD: {ctx.guild.name} CHANNEL: {ctx.channel.name}")
            except Exception:
                log_msg = "Exception occurred in `{0.command}` in DMs with a user".format(ctx)
            tb = format_exception(type(error), error, error.__traceback__)
            print(''.join(tb))
            error_logs.exception(log_msg + "".join(tb) + '\n\n')
            for error_channel_id in read_config('boterrchannelid'):
                err_channel = self.get_channel(int(error_channel_id))
                if err_channel:
                    await err_channel.send(log_msg + "\n```" + ''.join(tb) + "\n```")
                else:
                    console_logger.info("No error channel set!")

    async def is_log_registered(self, guild: discord.Guild, log_type):
        """Checks to see if a log channel is registered for a given guild"""
        if guild is None:
            return False
        async with self.db.acquire() as conn:
            log_channel_types = await conn.fetchrow(
                "SELECT column_name FROM information_schema.columns WHERE table_name = 'log_channels' AND column_name != 'guildid';")
            i = 0
            for channel in log_channel_types:
                if log_type == channel:
                    break
                i += 1

            if i > len(log_channel_types):
                return

            if (await conn.fetchrow(f"SELECT {log_type} FROM log_channels WHERE guildid = $1", guild.id)) is not None:
                return True
            else:
                return False

    async def on_ready(self):
        """Code that runs when the bot is starting up"""
        await self.prepare_db()
        self.load_extension("jishaku")  # de-bugging cog
        console_logger.info("jsk has been loaded")
        console_logger.info("Schema configured")
        if read_config("addons") is not None:
            for addon in read_config("addons"):
                try:
                    self.load_extension("addons." + addon)
                    console_logger.info(f"{addon} addon loaded")
                except Exception as e:
                    err_msg = f"Failed to load {addon}:\n{''.join(format_exception(type(e), e, e.__traceback__))}"
                    console_logger.exception(err_msg)

        if read_config("cogs") is not None:
            for cog in read_config("cogs"):
                try:
                    self.load_extension("cogs." + cog)
                    console_logger.info(f"{cog} cog loaded")

                except Exception as e:
                    err_msg = f"Failed to load {cog}:\n{''.join(format_exception(type(e), e, e.__traceback__))}"
                    console_logger.exception(err_msg)

        console_logger.info(f"LOGIN: Client logged in as {self.user.name}")
        self.loop.create_task(self.scheduler.run_timed_jobs())
        await self.change_presence(activity=discord.Game(read_config("activity")))


if __name__ == "__main__":
    bot = Terrygon()
    try:
        bot.run(read_config("token"))
    except Exception:
        print("Unable to login as a bot, please check your configuration for the bot token")
        sys.exit(1)
