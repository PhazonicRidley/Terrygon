import sys
from traceback import format_exception
import discord
from discord.ext import commands
import os
import asyncio
import re
import asyncpg
from utils import checks
from tabulate import tabulate
from logzero import setup_logger
import subprocess
import platform

botowner_console_logger = setup_logger(logfile="logs/botowner.log", maxBytes=1000000)


def nondaemonrestart():
    """Restarts the bot without a daemon"""
    print("Non-daemon restarting")
    os.execl(sys.executable, 'python3', 'main.py', *sys.argv[1:])


class BotOwner(commands.Cog):
    """
    Bot Owner commands
    """

    def __init__(self, bot):
        self.bot = bot

    @checks.is_bot_owner()
    @commands.command()
    async def unloadaddon(self, ctx, addon_in: str):
        """Unloads an addon.(Bot Owners only)"""
        addon = addon_in.lower()
        if addon == "botowner":
            await ctx.send("Cannot unload this addon commands")
            return

        try:
            addon = "addons." + addon
            self.bot.unload_extension(addon)
            botowner_console_logger.warning(f"{addon_in} unloaded")
            await ctx.send(f' {addon_in} addon unloaded.')

        except commands.ExtensionNotFound:
            return await ctx.send(f" Cannot find {addon_in} addon, is it in the `addons` folder?")

        except commands.ExtensionNotLoaded:
            return await ctx.send(f" {addon_in} addon is not loaded!")

        except Exception as e:
            # end all catch for errrors
            err_msg = "Failed to unload {}: {}".format(addon, "".join(format_exception(type(e), e, e.__traceback__)))
            botowner_console_logger.error(err_msg)
            await ctx.send('💢 Error trying to unload the addon:\n```\n{}: {}\n```'.format(type(e).__name__, e))

    @checks.is_bot_owner()
    @commands.command(aliases=['reloadaddon'], )
    async def loadaddon(self, ctx, addon_in: str):
        """(Re)loads an addon. (Bot Owners only)"""
        addon = "addons." + addon_in.lower()
        try:
            self.bot.unload_extension(addon)
            reloading = True
        except commands.ExtensionNotLoaded:
            reloading = False

        try:
            self.bot.load_extension(addon)
            botowner_console_logger.info(f"{addon} loaded")
            await ctx.send(f" {addon_in} addon reloaded." if reloading else f"{addon_in} addon loaded")

        except commands.ExtensionNotFound:
            return await ctx.send(f" {addon_in} was not found, is it in the `addons` folder?")

        except Exception as e:
            # end all catch for errors
            err_msg = " Failed to load {}: {}".format(addon, "".join(format_exception(type(e), e, e.__traceback__)))
            botowner_console_logger.exception(err_msg)
            await ctx.send('💢 Error trying to load the addon:\n```\n{}: {}\n```'.format(type(e).__name__, e))

    @checks.is_bot_owner()
    @commands.command(aliases=['reloadcog'], )
    async def loadcog(self, ctx, cog_in: str):
        """(Re)loads a cog. (Bot Owners only)"""

        cog = "cogs." + cog_in.lower()
        try:
            self.bot.unload_extension(cog)
            reloading = True
        except commands.ExtensionNotLoaded:
            reloading = False

        try:
            self.bot.load_extension(cog)
            botowner_console_logger.info(f" {cog_in} cog loaded")
            await ctx.send(f'✅ {cog_in} cog reloaded.' if reloading else f"{cog_in} cog loaded")

        except commands.ExtensionNotFound:
            return await ctx.send(f" {cog_in} cog cannot be found, is it in the `cogs` folder?")

        except Exception as e:
            # end all catch to failed loads
            err_msg = "Failed to load {}: {}".format(cog, "".join(format_exception(type(e), e, e.__traceback__)))
            botowner_console_logger.exception(err_msg)
            await ctx.send('💢 Error trying to load the cog:\n```\n{}: {}\n```'.format(type(e).__name__, e))

    @checks.is_bot_owner()
    @commands.command()
    async def unloadcog(self, ctx, cog_in: str):
        """Unloads an cog. (Bot Owner only)"""
        try:
            cog = "cogs." + cog_in.lower()
            self.bot.unload_extension(cog)
            botowner_console_logger.warning(f" {cog_in} cog unloaded")
            return await ctx.send(f"{cog_in} cog has been unloaded")
        except commands.ExtensionNotFound:
            return await ctx.send(f" Cannot find {cog_in} cog, is it in the `cog` folder?")

        except commands.ExtensionNotLoaded:
            return await ctx.send(f"{cog_in} cog is not loaded!")

        except Exception as e:
            # end all catch for errrors
            err_msg = "Failed to unload {}: {}".format(cog, "".join(format_exception(type(e), e, e.__traceback__)))
            botowner_console_logger.exception(err_msg)
            await ctx.send('💢 Error trying to unload the cog:\n```\n{}: {}\n```'.format(type(e).__name__, e))

    @commands.command(aliases=['listext', 'listextention', 'listcogs', 'listaddons'], )
    async def listextentions(self, ctx):
        """Lists modules that are loaded and unloaded"""
        unloaded_addons = [file[:-3] for file in os.listdir('addons') if file.endswith(".py")]
        unloaded_cogs = [file[:-3] for file in os.listdir('cogs') if file.endswith(".py")]
        loaded_extensions = self.bot.extensions
        loaded_addon_msg = ""
        unloaded_addon_msg = ""
        unloaded_cogs_msg = ""
        loaded_cogs_msg = ""
        for extension in loaded_extensions:
            if re.fullmatch('^addons.*', extension):
                loaded_addon_msg += f":white_check_mark: {extension[7:]}\n"
                if extension[7:] in unloaded_addons:
                    unloaded_addons.remove(extension[7:])

            elif re.fullmatch('^cogs.*', extension):
                loaded_cogs_msg += f":white_check_mark: {extension[5:]}\n"
                if (extension[5:]) in unloaded_cogs:
                    unloaded_cogs.remove(extension[5:])

        for addon in unloaded_addons:
            unloaded_addon_msg += f":x: {addon}\n"

        for cog in unloaded_cogs:
            unloaded_cogs_msg += f":x: {cog}\n"

        embed = discord.Embed(title=f"Extentions for {self.bot.user.name}", color=self.bot.user.color.value)
        embed.add_field(name="**Addons**", value=loaded_addon_msg + unloaded_addon_msg, inline=True)
        embed.add_field(name="**Custom Cogs**", value=loaded_cogs_msg + unloaded_cogs_msg, inline=True)
        await ctx.send(embed=embed)

    @checks.is_bot_owner()
    @commands.command()
    async def exit(self, ctx):
        """Shutdown the bot (Bot Owners only)"""

        await ctx.send("Shutting down")
        botowner_console_logger.info(f"Bot shutdown by {ctx.author}")
        # close db connection pool
        try:
            await self.bot.db.close()
            botowner_console_logger.info("Closed database connection pool gracefully")
        except Exception:
            botowner_console_logger.error("Database connection pool had trouble quitting!")

        finally:
            if platform.system() == 'Linux':
                try:
                    await self.bot.logout()
                    os.system('systemctl --user stop terrygon.service')  # TODO update name
                    sys.exit(0)

                except Exception:
                    pass
            await self.bot.logout()
            sys.exit(0)

    @checks.is_bot_owner()
    @commands.command()
    async def restart(self, ctx):
        """Restarts the bot (Bot Owners only)"""
        await ctx.send("Restarting...")
        await self.restartbot(ctx)

    async def restartbot(self, ctx):
        """Restarts the bot via systemd only for now"""
        try:
            await self.bot.db.close()
        except Exception:
            pass

        await asyncio.sleep(1)

        if platform.system() == 'Linux':
            await self.bot.logout()
            if os.system('systemctl --user restart terrygon.service') == 0:
                return await ctx.send("Restarted")

            else:
                nondaemonrestart()

        else:
            nondaemonrestart()

    @checks.is_bot_owner()
    @commands.command()
    async def sql(self, ctx, *, query):
        """Run queries to the db (Bot Owner only)"""
        async with self.bot.db.acquire() as conn:
            try:
                if 'select' in query.lower():
                    res = await conn.fetch(query)
                else:
                    res = await conn.execute(query)
                if not res:
                    return await ctx.send("Nothing found in database!")
                try:
                    table = tabulate(res, res[0].keys(), tablefmt='psql')
                except IndexError:
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

    @checks.is_bot_owner()
    @commands.command()
    async def pull(self, ctx):
        """Pulls latest code from github, bot owner's only"""
        await ctx.send("Pulling latest code....")
        subprocess.run(["git", "stash", "save"])
        subprocess.run(["git", "pull"])
        subprocess.run(["git", "stash", "clear"])
        await ctx.send("Restarting...")
        await self.restartbot(ctx)


def setup(bot):
    bot.add_cog(BotOwner(bot))
