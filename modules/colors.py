import typing
import discord
import webcolors
from discord.ext import commands
from utils import self_roles, checks, common


class Colors(commands.Cog):
    """Cog to manage server communal colors"""

    def __init__(self, bot):
        self.bot = bot

    async def color_mode_status(self, ctx: commands.Context):
        """Gives the current status of a guild's color mode"""
        mode = await self.bot.db.fetchval("SELECT mode FROM color_settings WHERE guild_id = $1", ctx.guild.id)
        await ctx.reply(f":art: Color mode is currently set to {mode.title()}")

    @commands.guild_only()
    @commands.group(name="colormode", invoke_without_command=True)
    async def color_mode(self, ctx: commands.Context, new_mode: str = None):
        """
        Switches the color mode. Valid options are: `disabled`, `communal`, `personal`.
        Communal - A color system that allows users to pick from a set of toggleable roles by using a keyword
        Personal - Each user gets their own color role of a hex that they choose. (Only for servers with 100 members and below)
        Disabled - Disables the entire color system for the server.
        """
        if not new_mode:
            await ctx.send_help(ctx.command)
            return await self.color_mode_status(ctx)
        current_mode = await self.bot.db.fetchval("SELECT mode FROM color_settings WHERE guild_id = $1", ctx.guild.id)
        new_mode = new_mode.lower()
        if new_mode == current_mode:
            await ctx.reply(f"Color system is already {current_mode.title()}")

        elif new_mode not in ('disabled', 'communal', 'personal'):
            await ctx.reply("Invalid option given. Valid options are: `disabled`, `communal`, `personal`.")

        else:
            await self.bot.db.execute("UPDATE color_settings SET mode = $1 WHERE guild_id = $2", new_mode, ctx.guild.id)
            await ctx.reply(f"Color mode now set to {new_mode.title()}")

    @commands.guild_only()
    @color_mode.command(name="status", aliases=['mode', 'currentmode'])
    async def mode_status(self, ctx: commands.Context):
        """Gets the current set mode of a server's color system."""
        await self.color_mode_status(ctx)

    @commands.guild_only()
    @commands.group(name="color", aliases=['colorme'], invoke_without_command=True)
    async def central_color(self, ctx: commands.Context, *, color: str = None):
        """
        Central color command to manage the entire color system.
        To change color:
        Communal - color argument should be the keyword of the color role you wish to toggle. ie `color red`
        Personal - color argument should be a valid hexadecimal value or RGB value you wish to apply to your personal role. ie `color #ff0000` or `color 255, 0, 0`
        """
        current_system = await self.bot.db.fetchval("SELECT mode FROM color_settings WHERE guild_id = $1", ctx.guild.id)
        if current_system == 'communal':
            if not color:
                return await self_roles.list_all_roles(ctx, 'communal_colors')
            await self.toggle_communal_color(ctx, color)
        elif current_system == 'personal':
            if not color:
                return await ctx.send_help(ctx.command)
            await self.toggle_personal_color(ctx, color)
        else:
            await ctx.reply(f"Color system is disabled for {ctx.guild.name}")

    async def toggle_communal_color(self, ctx: commands.Context, keyword: str):
        """Toggles a communal color"""
        author = ctx.author
        keyword = keyword.lower()
        role_id = await self.bot.db.fetchval("SELECT role_id FROM communal_colors WHERE guild_id = $1 AND keyword = $2",
                                             ctx.guild.id, keyword)
        role = ctx.guild.get_role(role_id)
        if not role:
            return await ctx.reply("Role does not exist.")

        if role in author.roles:
            try:
                await author.remove_roles(role, reason="Removed communal color role.")
            except discord.Forbidden:
                return await ctx.reply("Unable to manage roles.")

            return await ctx.reply(f"Removed {role.name}")

        try:
            await author.add_roles(role, reason="Added a communal color.")
        except discord.Forbidden:
            return await ctx.reply("Unable to manage roles.")

        communal_ids = await self.bot.db.fetch("SELECT role_id FROM communal_colors WHERE guild_id = $1", ctx.guild.id)
        communal_colors = [ctx.guild.get_role(r_id['role_id']) for r_id in communal_ids if
                           ctx.guild.get_role(r_id['role_id'])]
        current_colors = set(communal_colors) & set(author.roles)
        for r in current_colors:
            # should only run once
            if r == role:
                continue
            await author.remove_roles(r, reason="Swapping communal colors.")

        await ctx.reply(f"Color switched to {role.name}")

    async def toggle_personal_color(self, ctx: commands.Context, color_hex_in: str, user: discord.Member = None):
        """Sets personal colors."""
        if not user:
            user = ctx.author

        role_data = await self.bot.db.fetchrow(
            "SELECT role_id, color_hex FROM personal_colors WHERE guild_id = $1 AND user_id = $2", ctx.guild.id,
            user.id)
        move_role = False
        color_data = common.hex_to_color(color_hex_in)
        if not color_data:
            # attempt to parse input as RGB:
            rgb_triple = common.parse_rgb(color_hex_in)
            if not rgb_triple:
                return await ctx.reply("Invalid hex or RGB value.")
            else:
                color_data = common.hex_to_color(webcolors.rgb_to_hex(rgb_triple))
        if not role_data:
            # create role
            try:
                color_role = await ctx.guild.create_role(name=user.name, color=color_data[0])
            except discord.Forbidden:
                return await ctx.reply("Unable to manage roles.")
            res = await self_roles.add_self_role(ctx, 'personal_colors', color_role, user_id=user.id, color_hex=color_data[1])
            if res == 0:
                await user.add_roles(color_role, reason="Personal color role added.")
                await ctx.reply(f"Role created with hex `{color_data[1]}` and added to you.")

        else:
            # update hex of color role
            color_role = ctx.guild.get_role(role_data[0])
            if not color_role:
                await self.bot.db.execute("DELETE FROM personal_colors WHERE guild_id = $1 AND user_id = $2",
                                          ctx.guild.id, user.id)
                try:
                    await self.toggle_personal_color(ctx, color_hex_in, user)
                except RecursionError:
                    await ctx.reply("A recursion error has occurred, aborting! Please run this command again")
                return
            if color_role not in user.roles:
                try:
                    await user.add_roles(color_role)
                except discord.Forbidden:
                    return await ctx.reply("Unable to manage roles.")
            if role_data[1] != color_data[1]:
                try:
                    await color_role.edit(name=user.name, color=color_data[0], reason="Updating color.")
                except discord.Forbidden:
                    return await ctx.reply("Unable to manage roles.")
                await self.bot.db.execute(
                    "UPDATE personal_colors SET color_hex = $1 WHERE user_id = $2 AND role_id = $3", color_data[1],
                    ctx.author.id, color_role.id)
                await ctx.reply(f"Updated color to `{color_data[1]}`.")
            else:
                await ctx.reply("Color role hex is the same.")

        # check for highest colored role.
        top_color_role = ctx.guild.default_role
        user_roles = user.roles.copy()
        user_roles.reverse()
        for r in user_roles:
            if r.color.value != 0:
                if r.id == color_role.id:
                    break
                top_color_role = r
                move_role = True
                break
        if move_role and len(user.roles) > 2:
            await color_role.edit(position=top_color_role.position)

    @commands.guild_only()
    @checks.is_staff_or_perms("Mod", manage_roles=True)
    @central_color.command(name="add", aliases=['manualadd'])
    async def add_color_role(self, ctx: commands.Context, identifier: typing.Union[discord.Member, str],
                             role: typing.Union[discord.Role, str], color_string: str = None):
        """
        Adds a new color role
        Communal - adds a new communal color role (pass in a keyword for identifier)
        Personal - Manually adds a color role to a user. (pass in a user for identifier)
        """
        if not color_string and isinstance(role, str):
            return await ctx.send_help(ctx.command)
        elif isinstance(role, discord.Role) and not color_string:
            color_string = webcolors.rgb_to_hex((role.color.r, role.color.g, role.color.b))
        mode = await self.bot.db.fetchval("SELECT mode FROM color_settings WHERE guild_id = $1", ctx.guild.id)
        if mode == 'communal':
            if isinstance(identifier, str) and identifier in (
            "add", "manualadd", "remove", "del", "delete", "list", "info", "removeall", "delall", "deleteall"):
                return await ctx.reply(f"Cannot use {identifier} as a keyword. A command has this name.")
            color_tuple = common.hex_to_color(color_string)
            if not color_tuple:
                return await ctx.reply("Invalid hex given.")
            else:
                color_hex = color_tuple[1]
            await self_roles.add_self_role(ctx, 'communal_colors', role, keyword=identifier, color_hex=color_hex)
            return await ctx.reply(f"Communal color {role} set with color hex `{color_hex}`.")
        elif mode == 'personal':
            if isinstance(identifier, str):
                return await ctx.reply("Invalid user, please pass in a member of the server to create a role for.")
            await self.toggle_personal_color(ctx, color_string, identifier)

        else:
            await ctx.reply("Color system disabled, please enable to use this command.")

    @commands.guild_only()
    @checks.is_staff_or_perms("Owner", administator=True)
    @central_color.command(name="remove", aliases=['del', 'delete'])
    async def remove_color_role(self, ctx: commands.Context, identifier: typing.Union[discord.Member, str]):
        """Removes a color mode"""
        mode = await self.bot.db.fetchval("SELECT mode FROM color_settings WHERE guild_id = $1", ctx.guild.id)
        if mode == "communal":
            if not isinstance(identifier, str):
                return await ctx.reply("Invalid keyword given")
            if await self_roles.delete_self_role(ctx, 'communal_colors', ('keyword', identifier)) == -1:
                return
            await ctx.reply(f"Communal color {identifier} removed")

        elif mode == 'personal':
            if not isinstance(identifier, discord.Member):
                return await ctx.reply("Invalid user given.")

            if await self_roles.delete_self_role(ctx, 'personal_colors', ('user_id', identifier.id)) == -1:
                return
            await ctx.reply(f"Personal color role for {identifier} removed.")
        else:
            await ctx.reply("Color system disabled, please enable to use this command.")

    @commands.guild_only()
    @checks.is_staff_or_perms("Mod", manage_roles=True)
    @central_color.command(name="removeall", aliases=['delall', 'deleteall'])
    async def remove_all_colors(self, ctx: commands.Context):
        """Removes all color roles for the current mode."""
        mode = await self.bot.db.fetchval("SELECT mode FROM color_settings WHERE guild_id = $1", ctx.guild.id)
        if mode == 'disabled':
            return await ctx.reply("Color system disabled, please enable to use this command.")
        table = mode + "_colors"
        await self_roles.delete_all_roles(ctx, table)

    @commands.guild_only()
    @central_color.command(name="list")
    async def color_list(self, ctx: commands.Context):
        """Lists all colors for communal colors."""
        mode = await self.bot.db.fetchval("SELECT mode FROM color_settings WHERE guild_id = $1", ctx.guild.id)
        if mode == 'communal':
            await self_roles.list_all_roles(ctx, 'communal_colors')
        elif mode == "personal":
            await ctx.reply(
                "This command is for listing all the communal colors, if you would like to get information on a certain user's color role please use color info.")
        else:
            await ctx.reply("Color system disabled, please enable to use this command.")

    @commands.guild_only()
    @central_color.command(name="info")
    async def color_info(self, ctx: commands.Context, identifier: typing.Union[discord.Member, str] = None):
        """
        Gets info on a specific color role
        Communal - Identifier will be the keywords
        Personal - Identifier will be the user.
        """
        mode = await self.bot.db.fetchval("SELECT mode FROM color_settings WHERE guild_id = $1", ctx.guild.id)
        if mode == "communal":
            if not identifier:
                return await ctx.send_help(ctx.command)
            if not isinstance(identifier, str):
                return await ctx.reply("Invalid keyword")
            if await self_roles.get_role_info(ctx, "communal_colors", ("keyword", identifier)) == -1:
                return

        elif mode == "personal":
            if not identifier:
                identifier = ctx.author
            if not isinstance(identifier, discord.Member):
                return await ctx.reply("Invalid user")

            if await self_roles.get_role_info(ctx, "personal_colors", ("user_id", identifier.id)) == -1:
                return
        else:
            await ctx.reply("Color system disabled, please enable to use this command.")


async def setup(bot):
    await bot.add_cog(Colors(bot))
