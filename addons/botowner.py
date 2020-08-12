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

botownerconsolelogger = setup_logger(logfile="logs/botowner.log", maxBytes=1000000)


class BotOwner(commands.Cog):
    """
    Bot Owner commands
    """

    def __init__(self, bot):
        self.bot = bot

    @checks.is_bot_owner()
    @commands.command()
    async def unloadaddon(self, ctx, addonin: str):
        """Unloads an addon.(Bot Owners only)"""
        addon = addonin.lower()
        if addon == "botowner":
            await ctx.send("Cannot unload base commands")
            return

        try:
            addon = "addons." + addon
            self.bot.unload_extension(addon)
            botownerconsolelogger.warning(f"{addonin} unloaded")
            await ctx.send(f' {addonin} addon unloaded.')

        except commands.ExtensionNotFound:
            return await ctx.send(f" Cannot find {addonin} addon, is it in the `addons` folder?")

        except commands.ExtensionNotLoaded:
            return await ctx.send(f" {addonin} addon is not loaded!")

        except Exception as e:
            # end all catch for errrors
            errmsg = "Failed to unload {}: {}".format(addon, "".join(format_exception(type(e), e, e.__traceback__)))
            botownerconsolelogger.error(errmsg)
            await ctx.send('💢 Error trying to unload the addon:\n```\n{}: {}\n```'.format(type(e).__name__, e))

    @checks.is_bot_owner()
    @commands.command(aliases=['reloadaddon'], )
    async def loadaddon(self, ctx, addonin: str):
        """(Re)loads an addon. (Bot Owners only)"""
        addon = "addons." + addonin.lower()
        try:
            self.bot.unload_extension(addon)
            reloading = True
        except commands.ExtensionNotLoaded:
            reloading = False

        try:
            self.bot.load_extension(addon)
            botownerconsolelogger.info(f"{addon} loaded")
            await ctx.send(f" {addonin} addon reloaded." if reloading else f"{addonin} addon loaded")

        except commands.ExtensionNotFound:
            return await ctx.send(f" {addonin} was not found, is it in the `addons` folder?")

        except Exception as e:
            # end all catch for errors
            errmsg = " Failed to load {}: {}".format(addon, "".join(format_exception(type(e), e, e.__traceback__)))
            botownerconsolelogger.exception(errmsg)
            await ctx.send('💢 Error trying to load the addon:\n```\n{}: {}\n```'.format(type(e).__name__, e))

    @checks.is_bot_owner()
    @commands.command(aliases=['reloadcog'], )
    async def loadcog(self, ctx, cogin: str):
        """(Re)loads a cog. (Bot Owners only)"""

        cog = "cogs." + cogin.lower()
        try:
            self.bot.unload_extension(cog)
            reloading = True
        except commands.ExtensionNotLoaded:
            reloading = False

        try:
            self.bot.load_extension(cog)
            botownerconsolelogger.info(f" {cogin} cog loaded")
            await ctx.send(f'✅ {cogin} cog reloaded.' if reloading else f"{cogin} cog loaded")

        except commands.ExtensionNotFound:
            return await ctx.send(f" {cogin} cog cannot be found, is it in the `cogs` folder?")

        except Exception as e:
            # end all catch to failed loads
            errmsg = "Failed to load {}: {}".format(cog, "".join(format_exception(type(e), e, e.__traceback__)))
            botownerconsolelogger.exception(errmsg)
            await ctx.send('💢 Error trying to load the cog:\n```\n{}: {}\n```'.format(type(e).__name__, e))

    @checks.is_bot_owner()
    @commands.command()
    async def unloadcog(self, ctx, cogin: str):
        """Unloads an cog. (Bot Owner only)"""
        try:
            cog = "cogs." + cogin.lower()
            self.bot.unload_extension(cog)
            botownerconsolelogger.warning(f" {cogin} cog unloaded")
            return await ctx.send(f"{cogin} cog has been unloaded")
        except commands.ExtensionNotFound:
            return await ctx.send(f" Cannot find {cogin} cog, is it in the `cog` folder?")

        except commands.ExtensionNotLoaded:
            return await ctx.send(f"{cogin} cog is not loaded!")

        except Exception as e:
            # end all catch for errrors
            errmsg = "Failed to unload {}: {}".format(cog, "".join(format_exception(type(e), e, e.__traceback__)))
            botownerconsolelogger.exception(errmsg)
            await ctx.send('💢 Error trying to unload the cog:\n```\n{}: {}\n```'.format(type(e).__name__, e))

    @commands.command(aliases=['listext', 'listextention', 'listcogs', 'listaddons'], )
    async def listextentions(self, ctx):
        """Lists modules that are loaded and unloaded"""
        unloadedaddons = [file[:-3] for file in os.listdir('addons') if file.endswith(".py")]
        unloadedcogs = [file[:-3] for file in os.listdir('cogs') if file.endswith(".py")]
        loaded_extentions = self.bot.extensions
        loadedaddonmsg = ""
        unloadedaddonmsg = ""
        unloadedcogsmsg = ""
        loadedcogsmsg = ""
        for extention in loaded_extentions:
            if re.fullmatch('^addons.*', extention):
                loadedaddonmsg += f":white_check_mark: {extention[7:]}\n"
                if extention[7:] in unloadedaddons:
                    unloadedaddons.remove(extention[7:])

            elif re.fullmatch('^cogs.*', extention):
                loadedcogsmsg += f":white_check_mark: {extention[5:]}\n"
                if (extention[5:]) in unloadedcogs:
                    unloadedcogs.remove(extention[5:])

        for addon in unloadedaddons:
            unloadedaddonmsg += f":x: {addon}\n"

        for cog in unloadedcogs:
            unloadedcogsmsg += f":x: {cog}\n"

        embed = discord.Embed(title=f"Extentions for {self.bot.user.name}", color=self.bot.user.color.value)
        embed.add_field(name="**Addons**", value=loadedaddonmsg + unloadedaddonmsg, inline=True)
        embed.add_field(name="**Custom Cogs**", value=loadedcogsmsg + unloadedcogsmsg, inline=True)
        await ctx.send(embed=embed)

    @checks.is_bot_owner()
    @commands.command()
    async def exit(self, ctx):
        """Shutdown the bot (Bot Owners only)"""

        await ctx.send("Shutting down")
        botownerconsolelogger.info(f"Bot shutdown by {ctx.author}")
        # close db connection pool
        try:
            await self.bot.db.close()
            botownerconsolelogger.info("Closed database connection pool gracefully")
        except Exception:
            botownerconsolelogger.error("Database connection pool had trouble quitting!")

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

    def nondaemonrestart(self):
        """Restarts the bot without a daemon"""
        print("Non-daemon restarting")
        os.execl(sys.executable, 'python3', 'main.py', *sys.argv[1:])

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
                self.nondaemonrestart()

        else:
            self.nondaemonrestart()

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
                if len(res) > 2000:
                    await ctx.send("Output is too big!")
                    return
                else:
                    await ctx.send(f"```{table}```")
            except asyncpg.PostgresError:
                await ctx.send("Invalid SQL syntax")
            except TypeError:
                await ctx.send("Command has run, no output")

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
