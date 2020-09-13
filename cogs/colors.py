import discord
from discord.ext import commands, menus
import json
from utils import checks, paginator, errors
import webcolors
import typing
import io
from discord.utils import escape_mentions


class Colors(commands.Cog):
    """For handling user color modes in two different modes depending on the guild"""

    def __init__(self, bot):
        self.bot = bot

    async def cog_before_invoke(self, ctx):
        await self.setup_db_guild(ctx.guild.id)

    @commands.Cog.listener()
    async def on_member_join(self, member):
        async with self.bot.db.acquire() as conn:
            if await conn.fetchval("SELECT colormode FROM colors WHERE guildid = $1", member.guild.id):
                if member.guild.member_count > 100:
                    await conn.execute("UPDATE colors SET colormode = communal_role_data WHERE guildid = $1",
                                       member.guild.id)
                    await member.guild.owner.send(
                        "Your server has reached over 100 members, I have switched your color role mode to communal. I recommend setting up communal color roles with <this command> and making an announcement.")

                try:
                    role_id = (json.loads(
                        await conn.fetchval("SELECT personal_role_data->>$1 FROM colors WHERE guildid = $2",
                                            str(member.id), member.guild.id)))['roleid']
                    role = member.guild.get_role(role_id)
                    await member.add_roles(role)
                except TypeError:
                    pass

    # communal roles commands
    @commands.group(aliases=['communalcolor', 'communalcolour'], invoke_without_command=True)
    @commands.guild_only()
    async def communalcolors(self, ctx):
        """Commands related to the communal color role system (Only needed by servers that use the communal color system"""
        await ctx.send_help(ctx.command)

    @checks.is_staff_or_perms("Mod", manage_roles=True)
    @communalcolors.command()
    async def add(self, ctx, keyword, role: typing.Union[discord.Role, str], color_hex: str = None):
        """Sets a color role, adds one if it doesnt exist (Moderators or manage roles)"""

        if await self.check_color_mode(ctx.guild, 'communal'):
            return await ctx.send("Current color mode is not communal, thus you have no need for this!")

        if isinstance(role, discord.Role):
            color_hex = (str(hex(role.color.value)))[2:]

        else:
            if color_hex is None:
                raise commands.MissingRequiredArgument

        keyword = escape_mentions(keyword)
        if color_hex[0] != '#':
            color_hex = '#' + color_hex

        if len(color_hex) != 7:
            return await ctx.send("Invalid color hex, please try again")

        if isinstance(role, discord.Role):
            role_json = json.dumps({
                'roleid': role.id,
                'colorhex': color_hex
            })
            final_msg = f"{role.name} set as color role with hex, {color_hex}, use `.colorme {role.name}` to toggle it"
        else:
            role = await ctx.guild.create_role(name=role,
                                               color=discord.Color.from_rgb(*webcolors.hex_to_rgb(color_hex)))
            role_json = json.dumps({
                'roleid': role.id,
                'colorhex': color_hex
            })
            final_msg = f"Created role {role.name} and set it with color hex: {color_hex} `[p]color {role.name}` to toggle it"

        async with self.bot.db.acquire() as conn:
            current_com_colors = await conn.fetchval("SELECT communal_role_data FROM colors WHERE guildid = $1",
                                                     ctx.guild.id)
            if current_com_colors is None:
                final_query = "UPDATE colors SET communal_role_data = jsonb_build_object($1::TEXT, $2::jsonb) WHERE guildid = $3"
            else:
                final_query = "UPDATE colors SET communal_role_data = communal_role_data::jsonb || jsonb_build_object($1::TEXT, $2::jsonb) WHERE guildid = $3"
                # check for duplicate names
                if keyword in current_com_colors.keys():
                    return await ctx.send("Cannot duplicate color role keywords")

            await conn.execute(final_query, keyword, role_json, ctx.guild.id)
        await ctx.send(f"Added communal color {keyword}")

    @checks.is_staff_or_perms("Mod", manage_roles=True)
    @communalcolors.command(aliases=['del'])
    async def delete(self, ctx, keyword: str):
        """Removes a communal color and deletes the role if desired (Moderators or manage roles)"""
        if await self.check_color_mode(ctx.guild, 'communal'):
            return await ctx.send("Current color mode is not communal, thus you have no need for this!")

        async with self.bot.db.acquire() as conn:
            if await conn.fetchval("SELECT communal_role_data->>$1 FROM colors WHERE guildid = $2", keyword,
                                   ctx.guild.id) is None:
                return await ctx.send("Color does not exist in database for this server!")
            else:
                role_id = (json.loads(
                    await conn.fetchval("SELECT communal_role_data->>$1 FROM colors WHERE guildid = $2", keyword,
                                        ctx.guild.id)))['roleid']
                role = ctx.guild.get_role(role_id)
                res, msg = await paginator.YesNoMenu("Do you want to delete the role?").prompt(ctx)
                if role and res:
                    try:
                        await role.delete(reason="Deleted communal color role")
                        final_msg = "Deleted role and removed database entry"
                    except discord.Forbidden:
                        await ctx.send("Unable to delete role, check my permissions!")
                else:
                    final_msg = "Deleted database entry and did not delete role"
                await conn.execute(
                    "UPDATE colors SET communal_role_data = communal_role_data::jsonb - $1 WHERE guildid = $2", keyword,
                    ctx.guild.id)
                await msg.edit(content=final_msg)

    @communalcolors.command()
    async def list(self, ctx):
        """Lists communal color roles"""
        if await self.check_color_mode(ctx.guild, 'communal'):
            return await ctx.send("Current color mode is not communal, thus you have no need for this!")

        json_data = await self.bot.db.fetchval("SELECT communal_role_data FROM colors WHERE guildid = $1", ctx.guild.id)
        if not json_data:
            return await ctx.send("No communal color roles found, add some with `[p]communalcolors add`")
        embed = discord.Embed(title=f"Communal Color roles for {ctx.guild.name}", colour=ctx.author.color.value)
        color_list = []
        deleted_role = False
        del_role_str = ""  # just make sure we don't get unbound errors
        for keyword, role_data in json_data.items():
            role_data = json.loads(role_data)
            role = ctx.guild.get_role(role_data['roleid'])
            if not role:
                deleted_role = True
                del_role_str = f"- :warning: `{keyword}` has been deleted!\n"
                continue

            color_list.append(
                f"- **__Color Hex:__** {role_data['colorhex']} **__Role Name:__** {role.name} **__Keyword:__** `{keyword}`\n")

        if deleted_role:
            del_role_str += "\nPlease update these roles with `communalcolors add` or remove them with `communalcolors delete`"
            if len(del_role_str) >= 1250:
                embed.add_field(name="**Deleted color roles!**",
                                value="You have some deleted color roles, please see this file on which ones are deleted")
                await ctx.send(file=discord.File(io.StringIO(del_role_str), filename="delete-colors.txt"))
            else:
                embed.add_field(name="**Deleted color roles!**",
                                value=del_role_str)
        pages = paginator.ReactDeletePages(paginator.BasicEmbedMenu(color_list, per_page=6, embed=embed),
                                           clear_reactions_after=True, check_embeds=True)
        await pages.start(ctx)

    # personal role commands
    @commands.group(invoke_without_command=True, aliases=['personalcolors', 'personalcolours', 'personalcolour'])
    @commands.guild_only()
    async def personalcolor(self, ctx):
        """Commands relating to the personal color role system (Only needed by servers with a personal color system)"""
        await ctx.send_help(ctx.command)

    @checks.is_staff_or_perms("Owner", administrator=True)
    @personalcolor.command()
    async def delall(self, ctx):
        """Manually remove all personal color roles (Requires Administrator or Owner)"""
        res, msg = await paginator.YesNoMenu(
            "Really delete all personalized color roles from server and the database? This action is irreversible").prompt(
            ctx)
        if res:
            json_data = await self.bot.db.fetchval("SELECT personal_role_data FROM colors WHERE guildid = $1",
                                                  ctx.guild.id)
            if json_data is None:
                return await msg.edit(content="No personal color roles saved")
            for role_json in json_data.values():
                role = ctx.guild.get_role((json.loads(role_json))['roleid'])
                if role:
                    try:
                        await role.delete(reason=f"Clearing all personalized color roles, command ran by {ctx.author}")
                    except discord.Forbidden:
                        return await ctx.send("I do not have permission to delete roles")

            await self.bot.db.execute("UPDATE colors SET personal_role_data = NULL WHERE guildid = $1", ctx.guild.id)
            await msg.edit(content="All personal color roles deleted and removed from the database")
        else:
            await msg.edit(content="Cancelled")
            return

    @checks.is_staff_or_perms('Mod', manage_roles=True)
    @personalcolor.command()
    async def delmember(self, ctx, member: discord.Member = None):
        """Manually deletes a color role for a user (Requires you to be able to manage roles or Mod to delete another's color role)"""

        if member is None or member == ctx.author:
            member = ctx.author
        else:
            if not await checks.nondeco_is_staff_or_perms(ctx, 'Mod', manage_roles=True) and member != ctx.author:
                return await ctx.send("You cannot delete other people's color roles if you are not a mod")

        async with self.bot.db.acquire() as conn:
            db_entry = await conn.fetchval("SELECT personal_role_data->>$1 FROM colors WHERE guildid = $2", str(member.id), ctx.guild.id)
            if db_entry is None:
                return await ctx.send("This member does not have a color role!")
            role_entry = json.loads(db_entry)
            if role_entry is None:
                return await ctx.send("No entries found")

            del_query = "UPDATE colors SET personal_role_data = personal_role_data::jsonb - $1 WHERE guildid = $2"
            role = ctx.guild.get_role(role_entry['roleid'])
            if role is None:
                await ctx.send("Role does not exist on server, deleting from database")
                await conn.execute(del_query, str(member.id), ctx.guild.id)
                return
            else:
                try:
                    await role.delete(reason=f"Deleted by {ctx.author.name} ID: {ctx.author.id}")
                    await ctx.send("Role deleted and removed from database")
                except discord.Forbidden:
                    await ctx.send(
                        "Role could not be deleted, removing database entry, please manually remove this role and check my permissions")

                await conn.execute(del_query, str(member.id), ctx.guild.id)

    @checks.is_staff_or_perms("Mod", manage_roles=True)
    @personalcolor.command()
    async def manualadd(self, ctx, role: discord.Role, member: discord.Member):
        """Adds an already existing personal color to the database (Mod+ or manage_roles)"""
        if await self.check_color_mode(ctx.guild, 'personal'):
            return await ctx.send("Current color mode is not personal, thus you have no need for this!")

        await ctx.send((await self.add_personal_color_role(ctx, role, member))[0])

    @checks.is_staff_or_perms("Owner", administrator=True)
    @personalcolor.command()
    async def manualaddall(self, ctx):
        """Tries to add all existing personal color roles to the database, (Owners only or administrator perms)"""
        if await self.check_color_mode(ctx.guild, 'personal'):
            return await ctx.send("Current color mode is not personal, thus you have no need for this!")

        successful_adds = []
        for member in ctx.guild.members:
            for role in member.roles:
                if not member.bot and (role.color.value != 0 and role.name.lower() in member.name.lower()) or (
                        role.name == member.id):
                    if (await self.add_personal_color_role(ctx, role, member))[1] == 0:
                        successful_adds.append(f"`{member.name}`")

        embed = discord.Embed(color=ctx.me.color.value)
        embed.add_field(name="Users that had their color roles added:",
                        value=",".join(successful_adds) if len(successful_adds) != 0 else "No users added!")
        embed.set_footer(text=f"{len(successful_adds)} personal color roles added to the database" if len(
            successful_adds) != 1 else f"{len(successful_adds)} personal color role added to the database")
        await ctx.send(embed=embed)

    @personalcolor.command(aliases=['checkcolor', 'checkhex', 'getcolor', 'hex'])
    async def gethex(self, ctx, member: discord.Member = None):
        """Gets personal role color"""
        if await self.check_color_mode(ctx.guild, 'personal'):
            return await ctx.send("Current color mode is not personal, thus you have no need for this!")

        if member is None:
            member = ctx.author
        json_data = await self.bot.db.fetchval("SELECT personal_role_data->>$1 FROM colors WHERE guildid = $2",
                                              str(member.id), ctx.guild.id)
        if json_data:
            hex_color = str(json.loads(json_data)['colorhex']).zfill(6)
            embed = discord.Embed(title=f"Role color hex for {member}",
                                  colour=discord.Color.from_rgb(*webcolors.hex_to_rgb(hex_color)))
            embed.description = hex_color
            return await ctx.send(embed=embed)
        else:
            return await ctx.send("Member does not have role color saved!")

    @commands.guild_only()
    @commands.command(aliases=['colorme', 'color', 'colour'])
    async def switchrolecolor(self, ctx, new_color):
        """
        Changes your color. provide hex for personal color or keyword for communal color role

        Personal color mode: Argument is the color hex you would like to set your color role too. works with or without the # in the front. Will attempt to make it your highest colored role, run it again if it doesnt work right away

        Communal color mode: Argument is the keyword of the color role you want. If you would to remove your color role, specify the color you already have.

        To find out which colormode the server is in. use [p]curcolormode
        """
        cur_mode = await self.get_color_mode(ctx.guild)
        if cur_mode == "disabled":
            return await ctx.send("Color roles are disabled on this server")
        elif cur_mode == 'personal':
            # sets hex up and stops invalid entries

            if new_color[0] != '#':
                new_color = '#' + new_color

            if len(new_color) != 7:
                return await ctx.send("Invalid color hex, please try again!")

            async with self.bot.db.acquire() as conn:
                if await conn.fetchval("SELECT personal_role_data FROM colors WHERE guildid = $1",
                                       ctx.guild.id) is None:
                    final_query = "UPDATE colors SET personal_role_data = jsonb_build_object($1::BIGINT, $2::jsonb) WHERE guildid = $3"

                else:

                    final_query = "UPDATE colors SET personal_role_data = personal_role_data::jsonb || jsonb_build_object($1::BIGINT, $2::jsonb) WHERE guildid = $3"""

                try:
                    role_id = (json.loads(
                        await conn.fetchval("SELECT personal_role_data->>$1 FROM colors WHERE guildid = $2",
                                            str(ctx.author.id), ctx.guild.id)))['roleid']
                    role = ctx.guild.get_role(role_id)
                except TypeError:
                    role = None

                # get highest color role
                highest_color_role = ctx.guild.default_role
                move_role = False
                user_roles = ctx.author.roles.copy()
                user_roles.reverse()
                json_data = await self.bot.db.fetchval("SELECT personal_role_data->>$1 FROM colors WHERE guildid = $2", str(ctx.author.id), ctx.guild.id)
                color_role_id = json.loads(json_data)['roleid'] if json_data is not None else None
                for r in user_roles:
                    if r.color.value != 0:
                        if r.id == color_role_id:
                            break
                        highest_color_role = r
                        move_role = True
                        break
                if role is None:
                    # create role with user's name
                    try:
                        role = await ctx.guild.create_role(name=ctx.author.name, color=discord.Color.from_rgb(*webcolors.hex_to_rgb(new_color)), reason=f"Color role for {ctx.author.name}")
                        if move_role:
                            await role.edit(position=highest_color_role.position)
                        await ctx.author.add_roles(role)
                        await ctx.send("Role created and added it to you!")
                    except discord.Forbidden:
                        return await ctx.send("Unable to create and add role, please check my permissions")
                else:
                    # update existing role, move if needed
                    try:
                        await role.edit(name=ctx.author.name,
                                        color=discord.Color.from_rgb(*webcolors.hex_to_rgb(new_color)),
                                        reason=f"Color role for {ctx.author.name}")
                    except discord.Forbidden:
                        return await ctx.send("Unable to update role, check my permissions!")

                    if move_role:
                        try:
                            await role.edit(position=highest_color_role.position)
                        except discord.HTTPException:
                            return await ctx.send(
                                "Color updated, but I was unable to move your role to the highest color")

                    await ctx.send("Color updated!")

                    if role not in ctx.author.roles:
                        try:
                            await ctx.author.add_roles(role)
                        except discord.Forbidden:
                            await ctx.send("Cannot add roles, please check my permissions!")

                json_obj = json.dumps({
                    'colorhex': new_color,
                    'roleid': role.id
                })
                await conn.execute(final_query, ctx.author.id, json_obj, ctx.guild.id)

        else:
            # handles communal mode
            json_data = await self.bot.db.fetchval("SELECT communal_role_data->>$1 FROM colors WHERE guildid = $2", new_color, ctx.guild.id)
            if not json_data:
                return await ctx.send("Invalid communal color role option, to see options, run `communalcolors list`")

            json_data = json.loads(json_data)
            new_color_role = ctx.guild.get_role(json_data['roleid'])
            if not new_color_role:
                return await ctx.send(
                    f"Role does not exist, please re make it and add it to the bot, you can have the bot make it as well with `communalcolor add`. hexcolor for `{new_color}` is `#{json_data['colorhex']}")

            if new_color_role in ctx.author.roles:
                await ctx.author.remove_roles(new_color_role)
                return await ctx.send(f"Color {new_color} removed!")
            try:
                await ctx.author.add_roles(new_color_role)
                await ctx.send(f"Switched to {new_color} color")
            except discord.Forbidden:
                return await ctx.send("Unable to switch your colored roles due to a lack of permissions")

            communal_colors = await self.get_communal_roles(ctx.guild)
            cur_color = set(communal_colors) & set(ctx.author.roles)
            # just in case, *1 color at a time*
            for rid in cur_color:
                try:
                    role = ctx.guild.get_role(rid.id)
                    if role != new_color_role:
                        await ctx.author.remove_roles(role)
                except Exception:
                    pass

    @commands.command(aliases=['curmode', 'curcolormode'])
    async def currentcolormode(self, ctx):
        """Shows current guild's color mode"""
        cur_mode = await self.get_color_mode(ctx.guild)
        await ctx.send(f"{ctx.guild.name}'s current color role mode is {cur_mode.title()}")

    @checks.is_staff_or_perms("Owner", administrator=True)
    @commands.command()
    async def switchcolormode(self, ctx, mode):
        """Switches the server's color mode (Owners or administrator permissions) valid modes are `communal`, `personal`, or `disabled`"""
        async with self.bot.db.acquire() as conn:
            modes = ('communal', 'personal', 'disabled')
            cur_mode = await self.get_color_mode(ctx.guild)
            update_query = "UPDATE colors SET colormode = $1 WHERE guildid = $2"
            if mode not in modes:
                return await ctx.send("Invalid color mode, current modes are `communal`, `personal`, or `disabled`")
            elif cur_mode not in modes:
                return await ctx.send("Invalid mode saved, please contact a bot owner")

            elif mode == cur_mode:
                return await ctx.send(f"The current color mode is already set to {cur_mode}")

            # switches mode to personal if server count is under 100 members
            if mode == modes[1]:
                if ctx.guild.member_count > 100:
                    return await ctx.send("You cannot have personal color roles, your server is too big!")
                else:
                    await conn.execute(update_query, modes[1], ctx.guild.id)
                    return await ctx.send(f"Color mode switched to {modes[1]}")

            # switches color mode to communal
            else:
                await conn.execute(update_query, mode, ctx.guild.id)
                return await ctx.send(f"Color mode switched to {mode}")

    # util functions

    async def check_color_mode(self, guild: discord.Guild, required_mode):
        """check the color mode and makes sure the command is needed for certain commands"""
        cur_color_mode = await self.get_color_mode(guild)
        return cur_color_mode.lower() != required_mode.lower()

    async def get_color_mode(self, guild: discord.Guild) -> str:
        """Returns a guild's color mode"""
        return await self.bot.db.fetchval("SELECT colormode FROM colors WHERE guildid = $1", guild.id)

    async def add_personal_color_role(self, ctx: commands.Context, role: discord.Role, member: discord.Member):
        if await self.bot.db.fetchval("SELECT personal_role_data->>$1 FROM colors WHERE guildid = $2", str(member.id),
                                      ctx.guild.id):
            return "You already have a color role saved! use `color` to update it!", 1

        color_hex = (str(hex(role.color.value)))[2:].zfill(6)
        if color_hex[0] != '#':
            color_hex = '#' + color_hex

        role_data = json.dumps({
            'colorhex': color_hex,
            'roleid': role.id
        })
        async with self.bot.db.acquire() as conn:
            if await conn.fetchval("SELECT personal_role_data FROM colors WHERE guildid = $1", ctx.guild.id) is None:
                final_query = "UPDATE colors SET personal_role_data = jsonb_build_object($1::BIGINT, $2::jsonb) WHERE guildid = $3"
            else:
                final_query = "UPDATE colors SET personal_role_data = personal_role_data::jsonb || jsonb_build_object($1::BIGINT, $2::jsonb) WHERE guildid = $3"""

            await conn.execute(final_query, member.id, role_data, ctx.guild.id)
        if role not in member.roles:
            try:
                await member.add_roles(role)
            except discord.Forbidden:
                return "Cannot add roles, please check my permissions!", 1

        return "Color role manually added, update it with `color`. Run `color` if you need to move it to your highest colored role.", 0

    async def setup_db_guild(self, guild_id):
        """Adds a json config for a guild to store toggleable roles in"""
        async with self.bot.db.acquire() as conn:
            if await conn.fetchval("SELECT guildid FROM colors WHERE guildid = $1", guild_id) is None:
                await conn.execute("INSERT INTO colors (guildid) VALUES ($1)", guild_id)

    async def get_communal_roles(self, guild: discord.Guild) -> list:
        """Returns of list of a guild's communal color roles"""
        json_data = await self.bot.db.fetchval("SELECT communal_role_data FROM colors WHERE guildid = $1", guild.id)
        roles = []
        for i in json_data.values():
            role_id = json.loads(i)['roleid']
            role = guild.get_role(role_id)
            if role:
                roles.append(role)
        return roles


def setup(bot):
    bot.add_cog(Colors(bot))
