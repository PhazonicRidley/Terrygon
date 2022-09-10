import subprocess
import os
import sys
import asyncpg
import discord

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
            await ctx.reply("Cannot unload this module.")
            return

        try:
            addon = "modules." + module
            await self.bot.unload_extension(addon)
            self.bot.console_output_log.warning(f"{module} unloaded")
            await ctx.reply(f':x: {module} module unloaded.')

        except commands.ExtensionNotFound:
            return await ctx.reply(f":x: Cannot find {module}, is it in the `modules` folder?")

        except commands.ExtensionNotLoaded:
            return await ctx.reply(f":exclamation: {module} is not loaded!")

        except Exception as e:
            # end all catch for errors
            err_msg = "Failed to unload {}: {}".format(module, "".join(format_exception(type(e), e, e.__traceback__)))
            self.bot.error_log.error(err_msg)
            await ctx.reply('💢 Error trying to unload the addon:\n```\n{}: {}\n```'.format(type(e).__name__, e))

    @checks.is_bot_owner()
    @commands.command(aliases=['reload'])
    async def load(self, ctx, module_in: str):
        """(Re)loads an addon. (Bot Owners only)"""
        module = "modules." + module_in.lower()
        try:
            await self.bot.unload_extension(module)
            reloading = True
        except commands.ExtensionNotLoaded:
            reloading = False

        try:
            await self.bot.load_extension(module)
            self.bot.console_output_log.info(f"{module_in} loaded")
            await ctx.reply(
                f":white_check_mark: {module_in} reloaded." if reloading else f":white_check_mark: {module_in} loaded")

        except commands.ExtensionNotFound:
            return await ctx.reply(f":exclamation: {module_in} was not found, is it in the `modules` folder?")

        except Exception as e:
            # end all catch for errors
            err_msg = " Failed to load {}: {}".format(module, "".join(format_exception(type(e), e, e.__traceback__)))
            self.bot.error_log.exception(err_msg)
            await ctx.reply('💢 Error trying to load the addon:\n```\n{}: {}\n```'.format(type(e).__name__, e))

    @commands.command(alias=['listcogs', 'listcog'], name='listmodules')
    async def list_modules(self, ctx: commands.Context):
        """Lists the status of all modules installed on the bot"""
        # get modules, handle jsk completely seperately
        loaded_module_names = set([mod[8:] for mod in self.bot.extensions.keys() if mod[:8] == 'modules.'])
        all_module_names = set([x[:-3] for x in os.listdir('modules') if os.path.isfile(os.path.join('modules', x))])
        unload_module_names = all_module_names - loaded_module_names

        if 'jishaku' in self.bot.extensions.keys():
            loaded_module_names.add('jishaku')
        else:
            unload_module_names.add('jishaku')

        loaded_module_string = ""
        for module in loaded_module_names:
            loaded_module_string += f"✅ `{module}`\n"

        embed = discord.Embed(title="Module Status")
        embed.add_field(name="Loaded Modules", value=loaded_module_string, inline=True)
        if unload_module_names:
            unload_module_string = ""
            for module in unload_module_names:
                unload_module_string += f"❌ `{module}`\n"
            embed.add_field(name="Unloaded Modules", value=unload_module_string, inline=True)

        count_str = f"""Loaded modules: {len(loaded_module_names)}, Unloaded modules: {len(unload_module_names)}, Total
                    Modules: {len(loaded_module_names) + len(unload_module_names)}"""
        embed.set_footer(text=count_str)
        await ctx.reply(embed=embed)

    async def restart_bot(self, ctx: commands.Context):
        """Restarts the bot"""
        if os.environ.get("IS_DOCKER") and os.name == 'posix':
            await ctx.reply("Restarting....")
            self.bot.exit_code = 0
            await self.bot.close()

        elif os.name == 'posix':
            await ctx.reply("Restarting....")
            await self.bot.db.close()
            await self.bot.close()
            if os.system("systemctl --user restart terrygon.service") != 0:
                print("Please use systemd or docker.")
                sys.exit(-1)
        else:
            await ctx.reply("Restarting outside of docker container is not supported yet. Please restart manually.")

    @checks.is_bot_owner()
    @commands.command()
    async def restart(self, ctx: commands.Context):
        """Restarts the bot."""
        await self.restart_bot(ctx)

    @commands.command(name="shutdown")
    async def shutdown_bot(self, ctx: commands.Context):
        """Shuts the bot down"""
        if os.environ.get("IS_DOCKER") and os.name == 'posix':
            await ctx.reply("Shutting down....")
            self.bot.exit_code = 1
            await self.bot.close()
            sys.exit(1)  # returning 1 to show graceful shutdown.

        elif os.name == 'posix':
            await ctx.reply("Shutting down...")
            await self.bot.db.close()
            await self.bot.close()
            if os.system("systemctl --user shutdown terrygon.service") != 0:
                print("Please use systemd or docker.")
                sys.exit(1)
        else:
            await ctx.reply("Shutting down outside of a docker container is not yet supported.")

    @checks.is_bot_owner()
    @commands.command()
    async def pull(self, ctx: commands.Context):
        """Pulls latest code from github, bot owner's only"""
        await ctx.reply("Pulling latest code....")
        subprocess.run(["git", "stash", "save"])
        subprocess.run(["git", "pull"])
        subprocess.run(["git", "stash", "clear"])
        await self.restart_bot(ctx)

    # TODO: make command a bit more useful
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
                    return await ctx.reply("Nothing found in database!")
                try:
                    table = tabulate([tuple(x) for x in res], res[0].keys(), tablefmt='psql')
                except Exception:
                    table = res
                if len(res) > 1800:
                    await ctx.reply("Output is too big!")
                    return
                else:
                    await ctx.reply(f"```{table}```")
            except asyncpg.PostgresError as e:
                await ctx.reply(f"Postgres error: ```py{e.__traceback__}```")
            except TypeError:
                await ctx.reply("Command has ran, no output")


async def setup(bot):
    await bot.add_cog(BotOwner(bot))
