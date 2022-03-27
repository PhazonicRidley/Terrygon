import subprocess
import os
import sys
import asyncpg
from utils import checks
from tabulate import tabulate
from traceback import format_exception
from discord.ext import commands


class BotOwner(commands.Cog):
    """
    Bot Owner commands
    """

    def __init__(self, bot):
        self.bot = bot

    @checks.is_bot_owner()
    @commands.command()
    async def unload(self, ctx, module: str):
        """Unloads an addon.(Bot Owners only)"""
        module = module.lower()
        if module == "botowner":
            await ctx.send("Cannot unload this module.")
            return

        try:
            addon = "modules." + module
            self.bot.unload_extension(addon)
            self.bot.console_output_log.warning(f"{module} unloaded")
            await ctx.send(f':x: {module} module unloaded.')

        except commands.ExtensionNotFound:
            return await ctx.send(f":x: Cannot find {module}, is it in the `modules` folder?")

        except commands.ExtensionNotLoaded:
            return await ctx.send(f":exclamation: {module} is not loaded!")

        except Exception as e:
            # end all catch for errors
            err_msg = "Failed to unload {}: {}".format(module, "".join(format_exception(type(e), e, e.__traceback__)))
            self.bot.error_log.error(err_msg)
            await ctx.send('💢 Error trying to unload the addon:\n```\n{}: {}\n```'.format(type(e).__name__, e))

    @checks.is_bot_owner()
    @commands.command(aliases=['reload'])
    async def load(self, ctx, module_in: str):
        """(Re)loads an addon. (Bot Owners only)"""
        module = "modules." + module_in.lower()
        try:
            self.bot.unload_extension(module)
            reloading = True
        except commands.ExtensionNotLoaded:
            reloading = False

        try:
            self.bot.load_extension(module)
            self.bot.console_output_log.info(f"{module_in} loaded")
            await ctx.send(
                f":white_check_mark: {module_in} reloaded." if reloading else f":white_check_mark: {module_in} loaded")

        except commands.ExtensionNotFound:
            return await ctx.send(f":exclaimation: {module_in} was not found, is it in the `modules` folder?")

        except Exception as e:
            # end all catch for errors
            err_msg = " Failed to load {}: {}".format(module, "".join(format_exception(type(e), e, e.__traceback__)))
            self.bot.error_log.exception(err_msg)
            await ctx.send('💢 Error trying to load the addon:\n```\n{}: {}\n```'.format(type(e).__name__, e))

    async def restart_bot(self, ctx: commands.Context):
        """Restarts the bot"""
        if os.environ.get("IS_DOCKER") and os.name == 'posix':
            await ctx.send("Restarting....")
            self.bot.exit_code = 0
            await self.bot.close()

        elif os.name == 'posix':
            await ctx.send("Restarting....")
            await self.bot.db.close()
            await self.bot.close()
            if os.system("systemctl --user restart terrygon.service") != 0:
                print("Please use systemd or docker.")
                sys.exit(-1)
        else:
            await ctx.send("Restarting outside of docker container is not supported yet. Please restart manually.")

    @checks.is_bot_owner()
    @commands.command()
    async def restart(self, ctx: commands.Context):
        """Restarts the bot."""
        await self.restart_bot(ctx)

    @commands.command(name="shutdown")
    async def shutdown_bot(self, ctx: commands.Context):
        """Shuts the bot down"""
        if os.environ.get("IS_DOCKER") and os.name == 'posix':
            await ctx.send("Shutting down....")
            self.bot.exit_code = 1
            await self.bot.close()
            sys.exit(1)  # returning 1 to show graceful shutdown.

        elif os.name == 'posix':
            await ctx.send("Shutting down...")
            await self.bot.db.close()
            await self.bot.close()
            if os.system("systemctl --user shutdown terrygon.service") != 0:
                print("Please use systemd or docker.")
                sys.exit(1)
        else:
            await ctx.send("Shutting down outside of a docker container is not yet supported.")

    @checks.is_bot_owner()
    @commands.command()
    async def pull(self, ctx: commands.Context):
        """Pulls latest code from github, bot owner's only"""
        await ctx.send("Pulling latest code....")
        subprocess.run(["git", "stash", "save"])
        subprocess.run(["git", "pull"])
        subprocess.run(["git", "stash", "clear"])
        await self.restart_bot(ctx)

    @checks.is_bot_owner()
    @commands.command()
    async def sql(self, ctx, *, query):
        """Run queries to the db (Bot Owner only)"""
        # TODO: test once more stuff is implemented and database can be easily populated.
        async with self.bot.db.acquire() as conn:
            try:
                if 'select' in query.lower():
                    res = await conn.fetch(query)
                else:
                    res = await conn.execute(query)
                if not res:
                    return await ctx.send("Nothing found in database!")
                try:
                    table = tabulate([tuple(x) for x in res], res[0].keys(), tablefmt='psql')
                except Exception:
                    table = res
                if len(res) > 1800:
                    await ctx.send("Output is too big!")
                    return
                else:
                    await ctx.send(f"```{table}```")
            except asyncpg.PostgresError as e:
                await ctx.send(f"Postgres error: ```py{e.__traceback__}```")
            except TypeError:
                await ctx.send("Command has ran, no output")


async def setup(bot):
    await bot.add_cog(BotOwner(bot))
