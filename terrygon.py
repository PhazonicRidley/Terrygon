#!/usr/bin/env python3
import typing
from traceback import format_exception
import sys
import os
import discord
from discord.ext import commands, flags
from discord import app_commands
import asyncpg
import asyncio
from logzero import setup_logger, logger
import toml
from utils import errors, scheduler, checks, help
from utils.logger import TerrygonLogger
import json

# check if log folder and files exist
if not os.path.isdir("data/logs"):
    os.mkdir("data/logs")
    open("data/logs/error.log", "a").close()
    open("data/logs/console_output.log", "a").close()

else:
    if not os.path.isfile("data/logs/error.log") or not os.path.isfile("data/logs/console_output.log"):
        open("data/logs/error.log", "a").close()
        open("data/logs/console_output.log", "a").close()


async def create_pool():
    """Creates database connection pool."""

    async def configure_connection_codec(conn):
        await conn.set_type_codec('jsonb', encoder=json.dumps, decoder=json.loads, schema='pg_catalog')

    return await asyncpg.create_pool(read_config("credentials", "db"), init=configure_connection_codec,
                                     server_settings={'search_path': "terrygon"})


def read_config(block, config):
    """Reads configurations from config.toml"""
    output = toml.load(open("data/config.toml"), _dict=dict)
    return output[block][config]


# modified from https://gitlab.com/lightning-bot/Lightning/-/blob/v3/lightning.py#L42 and https://github.com/Rapptz/RoboDanny/blob/rewrite/bot.py#L44
async def _callable_prefix(bot, message: discord.Message):
    """Allows for a dynamic bot prefix"""
    default_prefix = read_config("info", 'default_prefix')
    if message.guild is None:
        return commands.when_mentioned_or(default_prefix)(bot, message)
    guild_prefixes = await bot.db.fetchval("SELECT prefixes FROM guild_settings WHERE guild_id = $1", message.guild.id)
    if guild_prefixes:
        guild_prefixes.append(default_prefix)
        return commands.when_mentioned_or(*guild_prefixes)(bot, message)
    else:
        return commands.when_mentioned_or(default_prefix)(bot, message)


class Terrygon(commands.Bot):
    """Main bot class"""

    def __init__(self):
        # set up loggers
        self.error_log = setup_logger(name="error_log", logfile="data/logs/error.log", maxBytes=100000)
        self.console_output_log = setup_logger(name="console_output_log", logfile="data/logs/console_output.log",
                                               maxBytes=100000)

        help_cmd = help.TerryHelp()
        super().__init__(command_prefix=_callable_prefix, description=read_config("info", "description"),
                         max_messages=10000,
                         help_command=help_cmd,
                         allowed_mentions=discord.AllowedMentions(everyone=False, users=True, roles=True),
                         intents=discord.Intents().all(), owner_ids=read_config("bot_management", "bot_owners"))

        # set up bot stdout logging, discord logging, and time event scheduling
        self.tree.error_log = self.error_log
        self.terrygon_logger = TerrygonLogger(self)
        self.console_output_log.info("Discord logger has been configured")
        self.scheduler = scheduler.Scheduler(self)
        self.console_output_log.info("Scheduler has started.")
        self.exit_code = 0
        self.db = None

    async def setup_hook(self) -> None:
        """Set up asynchronous coroutine"""
        try:
            # attempt to set up the database connection pool, quit out if cannot.
            self.db = await create_pool()
            self.console_output_log.info("Database pool has started!")
        except Exception as e:
            print("Unable to connect to the postgresql database, please check your configuration!")
            self.error_log.exception("".join(format_exception(type(e), e, e.__traceback__)))
            exit(-1)

        await self.prepare_db()
        self.console_output_log.info("Schema configured")
        await self.load_extension("jishaku")
        self.console_output_log.info("jsk has been loaded")  # de-bugging cog
        modules = read_config("info", "modules")
        if modules:
            for module in modules:
                try:
                    await self.load_extension("modules." + module)
                    self.console_output_log.info(f"{module} module loaded")
                except Exception as e:
                    err_msg = f"Failed to load the module {module}:\n{''.join(format_exception(type(e), e, e.__traceback__))}"
                    self.error_log.exception(err_msg)

        asyncio.create_task(self.scheduler.run_timed_jobs(), name="Timer Jobs Loop")
        self.console_output_log.info("Timers configured")
        self.tree.copy_global_to(guild=discord.Object(id=656294266867548160))
        await self.tree.sync(guild=discord.Object(id=656294266867548160))

    async def prepare_db(self):
        """Prepare our database for use"""
        async with self.db.acquire() as conn:
            try:
                with open("data/schema.sql", 'r') as schema:
                    try:
                        await conn.execute(schema.read())
                    except asyncpg.PostgresError as e:
                        err = "A SQL error has occurred while running the schema, traceback is:\n{}".format("".join(
                            format_exception(type(e), e, e.__traceback__)))
                        self.error_log.exception(err)
                        sys.exit(-1)

            except FileNotFoundError as e:
                self.error_log.exception("Unable to find schema.sql file traceback: {}\n").format(
                    "".join(format_exception(type(e), e, e.__traceback__)))
                sys.exit(-1)

    async def on_command_error(self, ctx, error):
        """Function to handle all command errors, event is called on error"""

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
            await ctx.reply("This command was used {:.2f}s ago and is on cooldown. Try again in {:.2f}s.".format(
                error.cooldown.per - error.retry_after, error.retry_after), ephemeral=True)

        # Handle commands that are attempted to be used outside a guild.
        elif isinstance(error, commands.errors.NoPrivateMessage):
            await ctx.reply("You cannot use this command outside of a server!")

        # handles a privileged command when a user without the right requirements attempts to use it.
        elif isinstance(error, errors.MissingStaffRoleOrPerms):
            msg = f"You do not have at least the {error.mod_role} role"
            if error.perms:
                msg += " or the following permissions: "
                for perm in error.perms:
                    msg += f"`{perm}` "
            msg += " and thus cannot use this command."
            await ctx.reply(msg, ephemeral=True)

        # handles command that require staff roles and none are saved.
        elif isinstance(error, errors.NoStaffRolesSaved):
            await ctx.reply("No staff roles in the database for this server please add some!", ephemeral=True)

        # handles all bot owner commands that are used by someone who is not a bot owner.
        elif isinstance(error, (errors.BotOwnerError, commands.errors.NotOwner)):
            await ctx.reply("You cannot use this as you are not a bot owner", ephemeral=True)

        # handles trusted commands used by untrusted users.
        elif isinstance(error, errors.UntrustedError):
            await ctx.reply("You are not a trusted user or a staff member and thus cannot use this!", ephemeral=True)

        elif isinstance(error, commands.ExtensionAlreadyLoaded):
            return

        # handles any uncaught command, posts traceback in the assigned bot errors channel.
        else:
            await ctx.send(f"An error occurred while processing the `{ctx.command.name}` command.", ephemeral=True)
            if ctx.guild:
                log_msg = f"Exception occurred in `{ctx.command}` in {ctx.channel.name}"
                self.error_log.error(
                    f"COMMAND: {ctx.command.name}, GUILD: {ctx.guild.name} CHANNEL: {ctx.channel.name}")
            else:
                # handle dm errors.
                log_msg = f"Exception occurred in `{ctx.command}` in DMs with a user"
                self.error_log.error(f"COMMAND: {ctx.command.name}, DMs with a user.")
            tb_string = "".join(format_exception(type(error), error, error.__traceback__))
            self.error_log.exception(tb_string + '\n\n')
            for error_channel_id in read_config("bot_management", 'bot_error_channels'):
                err_channel = self.get_channel(int(error_channel_id))
                if err_channel:
                    err_emb = discord.Embed(title=log_msg, description="\n```" + tb_string + "\n```",
                                            color=discord.Color.red())
                    await err_channel.send(embed=err_emb)
                else:
                    self.error_log.error("No error channel set!")

    async def on_ready(self):
        """Code that runs when the bot is starting up"""
        await self.change_presence(activity=discord.Game(read_config("info", "activity")))
        self.console_output_log.info(f"Client logged in as {self.user}")

    async def is_log_registered(self, guild: discord.Guild, log_type):
        """Checks to see if a log channel is registered for a given guild"""
        if guild is None:
            return False
        async with self.db.acquire() as conn:
            log_channel_types = await conn.fetchrow(
                "SELECT column_name FROM information_schema.columns WHERE table_name = 'channels' AND column_name != 'guild_id';")
            i = 0
            for channel in log_channel_types:
                if log_type == channel:
                    break
                i += 1

            if i > len(log_channel_types):
                return

            if (await conn.fetchrow(f"SELECT {log_type} FROM channels WHERE guild_id = $1", guild.id)) is not None:
                return True
            else:
                return False


async def main():
    bot = Terrygon()
    async with bot:
        await bot.start(read_config("credentials", "token"))


if __name__ == "__main__":
    asyncio.run(main())
