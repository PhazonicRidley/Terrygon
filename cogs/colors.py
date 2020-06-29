import discord
from discord.ext import commands, menus
import json
from utils import checks, paginator
import webcolors
import typing
import io
from discord.utils import escape_mentions


# TODO modularize

class YesNoMenu(menus.Menu):

    def __init__(self, initMsg):
        super().__init__(timeout=30.0)
        self.msg = initMsg
        self.result = None

    async def send_initial_message(self, ctx, channel):
        return await channel.send(self.msg)

    @menus.button('\N{WHITE HEAVY CHECK MARK}')
    async def yes(self, payload):
        self.result = True
        await self.clear_buttons(react=True)
        self.stop()

    @menus.button('\N{CROSS MARK}')
    async def no(self, payload):
        self.result = False
        await self.clear_buttons(react=True)
        self.stop()

    async def prompt(self, ctx):
        await self.start(ctx, wait=True)
        return self.result, self.message


class Colors(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    async def cog_before_invoke(self, ctx):
        await self.setupdbguild(ctx.guild.id)

    @commands.Cog.listener()
    async def on_member_join(self, member):
        if member.guild.member_count > 100:
            await self.bot.db.execute("UPDATE colors SET colormode = communal WHERE guildid = $1", member.guild.id)
            await member.guild.owner.send(
                "Your server has reached over 100 members, I have switched your color role mode to communal. I recommend setting up communal color roles with <this command> and making an announcement.")

        if (
                await self.bot.db.fetchval("SELECT colormode FROM colors WHERE guildid = $1",
                                           member.guild.id)) == 'personal':
            try:
                roleid = (json.loads(
                    await self.bot.db.fetchval("SELECT personal_role_data->>$1 FROM colors WHERE guildid = $2",
                                               str(member.id), member.guild.id)))['roleid']
                role = member.guild.get_role(roleid)
                await member.add_roles(role)
            except TypeError:
                pass

    # communal roles commands
    @commands.group(aliases=['communalcolor'], invoke_without_command=True)
    @commands.guild_only()
    async def communalcolors(self, ctx):
        """Commands related to the communal color role system"""
        await ctx.send_help(ctx.command)

    @checks.is_staff_or_perms("Mod", manage_roles=True)
    @communalcolors.command()
    async def add(self, ctx, keyword, role: typing.Union[discord.Role, str], colorhex: str = None):
        """Sets a color role, adds one if it doesnt exist (Requires you to be able to manage roles)"""
        if isinstance(role, discord.Role):
            colorhex = (str(hex(role.color.value)))[2:]

        else:
            if colorhex is None:
                raise commands.MissingRequiredArgument

        keyword = escape_mentions(keyword)
        if colorhex[0] != '#':
            colorhex = '#' + colorhex

        if len(colorhex) != 7:
            return await ctx.send("Invalid color hex, please try again")

        if isinstance(role, discord.Role):
            rolejsonobj = json.dumps({
                'roleid': role.id,
                'colorhex': colorhex
            })
            finalmsg = f"{role.name} set as color role with hex, {colorhex}, use `.colorme {role.name}` to toggle it"
        else:
            role = await ctx.guild.create_role(name=role, color=discord.Color.from_rgb(*webcolors.hex_to_rgb(colorhex)))
            rolejsonobj = json.dumps({
                'roleid': role.id,
                'colorhex': colorhex
            })
            finalmsg = f"Created role {role.name} and set it with color hex: {colorhex} `.colorme {role.name}` to toggle it"

        async with self.bot.db.acquire() as conn:
            currentcomcolors = await conn.fetchval("SELECT communal_role_data FROM colors WHERE guildid = $1",
                                                   ctx.guild.id)
            if currentcomcolors is None:
                finalquery = "UPDATE colors SET communal_role_data = jsonb_build_object($1::TEXT, $2::jsonb) WHERE guildid = $3"
            else:
                finalquery = "UPDATE colors SET communal_role_data = communal_role_data::jsonb || jsonb_build_object($1::TEXT, $2::jsonb) WHERE guildid = $3"""
                # check for duplicate names
                if keyword in currentcomcolors.keys():
                    return await ctx.send("Cannot duplicate color role keywords")

            await conn.execute(finalquery, keyword, rolejsonobj, ctx.guild.id)
        await ctx.send(f"Added communal color {keyword}")

    @checks.is_staff_or_perms("Mod", manage_roles=True)
    @communalcolors.command(aliases=['del'])
    async def delete(self, ctx, keyword: str):
        """Removes a communal color and deletes the role if desired (Requires you to be able to manage roles)"""
        async with self.bot.db.acquire() as conn:
            if await conn.fetchval("SELECT communal_role_data->>$1 FROM colors WHERE guildid = $2", keyword,
                                   ctx.guild.id) is None:
                return await ctx.send("Color does not exist in database for this server!")
            else:
                roleid = (json.loads(
                    await conn.fetchval("SELECT communal_role_data->>$1 FROM colors WHERE guildid = $2", keyword,
                                        ctx.guild.id)))['roleid']
                role = ctx.guild.get_role(roleid)
                res, msg = await YesNoMenu("Do you want to delete the role?").prompt(ctx)
                if role and res:
                    try:
                        await role.delete(reason="Deleted communal color role")
                        finalmsg = "Deleted role and removed database entry"
                    except discord.Forbidden:
                        await ctx.send("Unable to delete role, check my permissions!")
                else:
                    finalmsg = "Deleted database entry and did not delete role"
                await conn.execute(
                    "UPDATE colors SET communal_role_data = communal_role_data::jsonb - $1 WHERE guildid = $2", keyword,
                    ctx.guild.id)
                await msg.edit(content=finalmsg)

    @communalcolors.command()
    async def list(self, ctx):
        """Lists communal color roles"""
        jsondata = await self.bot.db.fetchval("SELECT communal_role_data FROM colors WHERE guildid = $1", ctx.guild.id)
        if not jsondata:
            return await ctx.send("No communal color roles found, add some with `.communalcolors add`")
        embed = discord.Embed(title=f"Communal Color roles for {ctx.guild.name}", colour=ctx.author.color.value)
        colorlist = []
        deletedrole = False
        delrolestr = ""  # just make sure we dont get unbound errors
        for keyword, roledata in jsondata.items():
            roledata = json.loads(roledata)
            role = ctx.guild.get_role(roledata['roleid'])
            if not role:
                deletedrole = True
                delrolestr = f"- :warning: `{keyword}` has been deleted!\n"
                continue

            colorlist.append(
                f"- **__Color Hex:__** {roledata['colorhex']} **__Role Name:__** {role.name} **__Keyword:__** `{keyword}`\n")

        if deletedrole:
            delrolestr += "\nPlease update these roles with `communalcolors add` or remove them with `communalcolors delete`"
            if len(delrolestr) >= 1250:
                embed.add_field(name="**Deleted color roles!**",
                                value="You have some deleted color roles, please see this file on which ones are deleted")
                await ctx.send(file=discord.File(io.StringIO(delrolestr), filename="delete-colors.txt"))
            else:
                embed.add_field(name="**Deleted color roles!**",
                                value=delrolestr)
        pages = paginator.ReactDeletePages(paginator.BasicEmbedMenu(colorlist, per_page=6, embed=embed),
                                           clear_reactions_after=True, check_embeds=True)
        await pages.start(ctx)

    # personal role commands
    @commands.group(invoke_without_command=True, aliases=['personalrole', 'personalcolors'])
    @commands.guild_only()
    async def personalcolor(self, ctx):
        """Commands relating to the personal color role system (Only needed by servers with a personal color system)"""
        await ctx.send_help(ctx.command)

    @checks.is_staff_or_perms("Owner", administrator=True)
    @personalcolor.command()
    async def delall(self, ctx):
        """Manually remove all personal color roles (Requires Administrator or Owner)"""
        res, msg = await YesNoMenu(
            "Really delete all personalized color roles from server and the database? This action is irreversible").prompt(
            ctx)
        if res:
            jsondata = await self.bot.db.fetchval("SELECT personal_role_data FROM colors WHERE guildid = $1",
                                                  ctx.guild.id)
            if jsondata is None:
                return await msg.edit(content="No personal color roles saved")
            for rolejson in jsondata.values():
                role = ctx.guild.get_role((json.loads(rolejson))['roleid'])
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

    @personalcolor.command()
    async def delmember(self, ctx, member: discord.Member = None):
        """Manually deletes a color role for a user (Requires you to be able to manage roles or Mod)"""
        if member is None or member == ctx.author:
            member = ctx.author
        else:
            if not await checks.nondeco_is_staff_or_perms(ctx, 'Mod', manage_roles=True) and member != ctx.author:
                return await ctx.send("You cannot delete other people's color roles if you are not a mod")

        async with self.bot.db.acquire() as conn:
            dbentry = await conn.fetchval("SELECT personal_role_data->>$1 FROM colors WHERE guildid = $2",
                                          str(member.id),
                                          ctx.guild.id)
            if dbentry is None:
                return await ctx.send("This member does not have a color role!")
            roleentry = json.loads(dbentry)
            if roleentry is None:
                return await ctx.send("No entries found")

            delquery = "UPDATE colors SET personal_role_data = personal_role_data::jsonb - $1 WHERE guildid = $2"
            role = ctx.guild.get_role(roleentry['roleid'])
            if role is None:
                await ctx.send("Role does not exist on server, deleting from database")
                await conn.execute(delquery, str(member.id), ctx.guild.id)
                return
            else:
                try:
                    await role.delete(reason=f"Deleted by {ctx.author.name} ID: {ctx.author.id}")
                    await ctx.send("Role deleted and removed from database")
                except discord.Forbidden:
                    await ctx.send(
                        "Role could not be deleted, removing database entry, please manually remove this role and check my permissions")

                await conn.execute(delquery, str(member.id), ctx.guild.id)

    @checks.is_staff_or_perms("Mod", manage_roles=True)
    @personalcolor.command()
    async def manualadd(self, ctx, role: discord.Role, member: discord.Member):
        """Adds an already existing personal color to the database (Mod+ or manage_roles)"""
        if await self.bot.db.fetchval("SELECT personal_role_data->>$1 FROM colors WHERE guildid = $2", str(member.id),
                                ctx.guild.id):
            return await ctx.send("You already have a color role saved! use `color` to update it!")

        colorhex = (str(hex(role.color.value)))[2:]
        if colorhex[0] != '#':
            colorhex = '#' + colorhex

        roledata = json.dumps({
            'colorhex': colorhex,
            'roleid': role.id
        })
        async with self.bot.db.acquire() as conn:
            if await conn.fetchval("SELECT personal_role_data FROM colors WHERE guildid = $1",
                                   ctx.guild.id) is None:
                finalquery = "UPDATE colors SET personal_role_data = jsonb_build_object($1::BIGINT, $2::jsonb) WHERE guildid = $3"

            else:

                finalquery = "UPDATE colors SET personal_role_data = personal_role_data::jsonb || jsonb_build_object($1::BIGINT, $2::jsonb) WHERE guildid = $3"""

            await conn.execute(finalquery, member.id, roledata, ctx.guild.id)
        await ctx.send(
            "Color role manually added, update it with `color` not your highest color role? run `color` to move it.")
        if role not in member.roles:
            try:
                await member.add_roles(role)
            except discord.Forbidden:
                await ctx.send("Cannot add roles, please check my permissions!")

    @personalcolor.command(aliases=['checkcolor', 'checkhex', 'getcolor', 'hex'])
    async def gethex(self, ctx, member: discord.Member = None):
        """Gets personal role color"""
        if member is None:
            member = ctx.author
        jsondata = await self.bot.db.fetchval("SELECT personal_role_data->>$1 FROM colors WHERE guildid = $2",
                                              str(member.id), ctx.guild.id)
        if jsondata:
            hexcolor = str(json.loads(jsondata)['colorhex']).zfill(6)
            embed = discord.Embed(title=f"Role color hex for {member}",
                                  colour=discord.Color.from_rgb(*webcolors.hex_to_rgb(hexcolor)))
            embed.description = hexcolor
            return await ctx.send(embed=embed)
        else:
            return await ctx.send("Member does not have role color saved!")

    @commands.guild_only()
    @commands.command(aliases=['colorme', 'color'])
    async def switchrolecolor(self, ctx, newcolor):
        """
        Changes your color. provide hex for personal color or keyword for communal color role

        Personal color mode: Argument is the color hex you would like to set your color role too. works with or without the # in the front. Will attempt to make it your highest colored role, run it again if it doesnt work right away

        Communal color mode: Argument is the keyword of the color role you want. If you would to remove your color role, specify the color you already have.
        """
        curmode = await self.bot.db.fetchval("SELECT colormode FROM colors WHERE guildid = $1", ctx.guild.id)

        if curmode == 'personal':
            # sets hex up and stops invalid entries

            if newcolor[0] != '#':
                newcolor = '#' + newcolor

            if len(newcolor) != 7:
                return await ctx.send("Invalid color hex, please try again!")

            async with self.bot.db.acquire() as conn:
                if await conn.fetchval("SELECT personal_role_data FROM colors WHERE guildid = $1",
                                       ctx.guild.id) is None:
                    finalquery = "UPDATE colors SET personal_role_data = jsonb_build_object($1::BIGINT, $2::jsonb) WHERE guildid = $3"

                else:

                    finalquery = "UPDATE colors SET personal_role_data = personal_role_data::jsonb || jsonb_build_object($1::BIGINT, $2::jsonb) WHERE guildid = $3"""

                try:
                    roleid = (json.loads(
                        await conn.fetchval("SELECT personal_role_data->>$1 FROM colors WHERE guildid = $2",
                                            str(ctx.author.id), ctx.guild.id)))['roleid']
                    role = ctx.guild.get_role(roleid)
                except TypeError:
                    role = None

                # TODO refactor and rewrite at a later time
                # get highest color role
                highestcolorrole = ctx.guild.default_role
                moverole = False
                uroles = ctx.author.roles.copy()
                uroles.reverse()
                jsondata = await self.bot.db.fetchval("SELECT personal_role_data->>$1 FROM colors WHERE guildid = $2",
                                                      str(ctx.author.id), ctx.guild.id)
                colorroleid = json.loads(jsondata)['roleid'] if jsondata is not None else None
                # print(uroles)
                for r in uroles:
                    if r.color.value != 0 and r.id != colorroleid:
                        # print(f"r is {r.name}")
                        highestcolorrole = r
                        moverole = True
                        break
                # print(highestcolorrole.name)
                # print(f"Move role: {moverole}")
                if role is None:
                    # create role with user's name
                    try:
                        role = await ctx.guild.create_role(name=ctx.author.name, color=discord.Color.from_rgb(
                            *webcolors.hex_to_rgb(newcolor)), reason=f"Color role for {ctx.author.name}")
                        if moverole:
                            await role.edit(position=highestcolorrole.position)
                        # print(f"Moved color role to: {role.position}")
                        await ctx.author.add_roles(role)
                        await ctx.send("Role created and added it to you!")
                    except discord.Forbidden:
                        return await ctx.send("Unable to create and add role, please check my permissions")
                else:
                    # update existing role, move if needed
                    try:
                        await role.edit(name=ctx.author.name, position=highestcolorrole.position,
                                        color=discord.Color.from_rgb(*webcolors.hex_to_rgb(newcolor)),
                                        reason=f"Color role for {ctx.author.name}")
                        # print(f"Edited color role pos: {role.position}")
                    except Exception:
                        try:
                            await role.edit(name=ctx.author.name,
                                            color=discord.Color.from_rgb(*webcolors.hex_to_rgb(newcolor)),
                                            reason=f"Color role for {ctx.author.name}")
                        except discord.Forbidden:
                            return await ctx.send("Could not update your roles, check my permissions!")
                        # print("Role did not move!")
                        await ctx.send(
                            "I was unable to move your role as your highest color role, please check configurations, role hierarchies, and my permissions")
                    await ctx.send("Color updated!")

                    if role not in ctx.author.roles:
                        try:
                            await ctx.author.add_roles(role)
                        except discord.Forbidden:
                            await ctx.send("Cannot add roles, please check my permissions!")

                jsonobj = json.dumps({
                    'colorhex': newcolor,
                    'roleid': role.id
                })
                await conn.execute(finalquery, ctx.author.id, jsonobj, ctx.guild.id)

        else:
            # handles communal mode
            jsondata = await self.bot.db.fetchval("SELECT communal_role_data->>$1 FROM colors WHERE guildid = $2",
                                                  newcolor, ctx.guild.id)
            if not jsondata:
                return await ctx.send("Invalid communal color role option, to see options, run `communalcolors list`")

            jsondata = json.loads(jsondata)
            newcolorrole = ctx.guild.get_role(jsondata['roleid'])
            if not newcolorrole:
                return await ctx.send(
                    f"Role does not exist, please re make it and add it to the bot, you can have the bot make it as well with `communalcolor add`. hexcolor for `{newcolor}` is `#{jsondata['colorhex']}")

            if newcolorrole in ctx.author.roles:
                await ctx.author.remove_roles(newcolorrole)
                return await ctx.send(f"Color {newcolor} removed!")
            try:
                await ctx.author.add_roles(newcolorrole)
                await ctx.send(f"Switched to {newcolor} color")
            except discord.Forbidden:
                return await ctx.send("Unable to switch your colored roles due to a lack of permissions")

            communalcolors = await self.getcommunalroles(ctx.guild)
            curcolor = set(communalcolors) & set(ctx.author.roles)
            print(curcolor)
            # just in case, *1 color at a time*
            for rid in curcolor:
                try:
                    role = ctx.guild.get_role(rid.id)
                    if role != newcolorrole:
                        await ctx.author.remove_roles(role)
                except Exception:
                    pass

    @commands.command(aliases=['curmode', 'curcolormode'])
    async def currentcolormode(self, ctx):
        curmode = await self.bot.db.fetchval("SELECT colormode FROM colors WHERE guildid = $1", ctx.guild.id)
        await ctx.send(f"{ctx.guild.name}'s current color role mode is {curmode.title()}")

    @checks.is_staff_or_perms("Owner", administrator=True)
    @commands.command()
    async def switchcolormode(self, ctx):
        async with self.bot.db.acquire() as conn:
            modes = ('communal', 'personal')
            curmode = await conn.fetchval("SELECT colormode FROM colors WHERE guildid = $1", ctx.guild.id)
            updatequery = "UPDATE colors SET colormode = $1 WHERE guildid = $2"
            if curmode not in modes:
                return await ctx.send("Something went wrong!")  # just in case!

            # switches mode to personal if server count is under 100 members
            if curmode == modes[0]:
                if ctx.guild.member_count > 100:
                    return await ctx.send("You cannot have personal color roles, your server is too big!")
                else:
                    await conn.execute(updatequery, modes[1], ctx.guild.id)
                    return await ctx.send(f"Color mode switched to {modes[1]}")

            # switches color mode to communal
            else:
                await conn.execute(updatequery, modes[0], ctx.guild.id)
                return await ctx.send(f"Color mode switched to {modes[0]}")

    # util functions
    async def setupdbguild(self, guildid):
        """Adds a json config for a guild to store toggleable roles in"""
        async with self.bot.db.acquire() as conn:
            if await conn.fetchval("SELECT guildid FROM colors WHERE guildid = $1", guildid) is None:
                await conn.execute("INSERT INTO colors (guildid) VALUES ($1)", guildid)

    async def getcommunalroles(self, guild: discord.Guild) -> list:
        """Returns of list of a guild's communal color roles"""
        jsondata = await self.bot.db.fetchval("SELECT communal_role_data FROM colors WHERE guildid = $1", guild.id)
        roles = []
        for i in jsondata.values():
            roleid = json.loads(i)['roleid']
            role = guild.get_role(roleid)
            if role:
                roles.append(role)

        return roles


def setup(bot):
    bot.add_cog(Colors(bot))
