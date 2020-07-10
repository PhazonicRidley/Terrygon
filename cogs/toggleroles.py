import discord
from discord.ext import commands, menus
from discord.utils import escape_mentions
import json
import typing
import io
from utils import checks, paginator

# TODO modularize


class ToggleRoles(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    # temporary, clean up later
    async def cog_before_invoke(self, ctx):
        await self.setupdbguild(ctx.guild.id)

    @commands.command()
    async def togglerole(self, ctx, keyword: str = None):
        """Toggle a role!"""
        if keyword is None:
            return await self.listroles(ctx)

        async with self.bot.db.acquire() as conn:
            jsonroleentry = await conn.fetchval("SELECT roles->>$1 FROM toggleroles WHERE guildid = $2", keyword,
                                                ctx.guild.id)
            if jsonroleentry is None:
                return await ctx.send("This keyword doesn't match any saved roles. Did you spell it right?")

            roleid = json.loads(jsonroleentry)['roleid']

            role = ctx.guild.get_role(roleid)
            if not role:
                return await ctx.send(
                    "Role does not exist! Please have a staff member remake the role update the database with `addtogglerole`")

            if role not in ctx.author.roles:
                try:
                    await ctx.author.add_roles(role)
                    await ctx.send(f"Joined {role.name}!")
                except discord.Forbidden:
                    await ctx.send("Unable to add roles!")
            else:
                try:
                    await ctx.author.remove_roles(role)
                    await ctx.send(f"Left {role.name}!")
                except discord.Forbidden:
                    await ctx.send("Unable to remove roles!")

    async def listroles(self, ctx):
        """Lists a guild's toggleable roles"""
        roles = await self.getrolesfromdb(ctx.guild.id)
        if not roles:
            return await ctx.send("No toggleable roles found, add some with `addtogglerole`")
        embed = discord.Embed(title=f"Toggleable roles for {ctx.guild.name}", colour=ctx.author.color.value)
        roleinfolist = []
        deletedrole = False
        delrolestr = ""  # just make sure we dont get unbound errors
        for keyword, roledata in roles.items():
            roledata = json.loads(roledata)
            emoji = '' if roledata['emoji'] is None else str(roledata['emoji'])
            role = ctx.guild.get_role(roledata['roleid'])
            if not role:
                deletedrole = True
                delrolestr = f"- :warning: `{escape_mentions(keyword)}` has been deleted!\n"
                continue

            roleinfolist.append(f"- {emoji} **__Role:__** {role.name} **__Description:__** {roledata['description']} **__Keyword:__** `{keyword}`\n")

        if deletedrole:
            delrolestr += "\nPlease update these roles with `addtogglerole` or deleted them with `deltogglerole`"
            if len(delrolestr) >= 1250:
                embed.add_field("**Deleted Toggle roles!**", value="You have deleted toggle roles, see this text file on which ones they are")
                await ctx.send(file=discord.File(io.StringIO(delrolestr), filename='deleted-toggleroles.txt'))
            else:
                embed.add_field(name="**Deleted toggle roles!**",
                                value=delrolestr)

        pages = paginator.ReactDeletePages(paginator.BasicEmbedMenu(roleinfolist, per_page=8, embed=embed), clear_reactions_after=True, check_embeds=True)
        await pages.start(ctx)


        #await ctx.send(embed=embed)

    @checks.is_staff_or_perms("Mod", manage_roles=True)
    @commands.command()
    async def deltogglerole(self, ctx, keyword: str):
        """Removes a toggleable role from the database (Mod+ only)"""
        async with self.bot.db.acquire() as conn:

            if await conn.fetchval("SELECT roles->>$1 FROM toggleroles WHERE guildid = $2", keyword,
                                   ctx.guild.id) is None:
                return await ctx.send("Role does not exist in database for this server!")
            else:
                roleid = (json.loads(await conn.fetchval("SELECT roles->>$1 FROM toggleroles WHERE guildid = $2", keyword, ctx.guild.id)))['roleid']
                role = ctx.guild.get_role(roleid)
                await conn.execute("UPDATE toggleroles SET roles = roles::jsonb - $1 WHERE guildid = $2", keyword,
                                   ctx.guild.id)
                await ctx.send("Role has been removed!")

        if role:
            res, msg = await paginator.YesNoMenu(f"Would you like to delete the {role.name} role?").prompt(ctx)
            if res:
                try:
                    await msg.edit(content=f"{role.name} role deleted")
                    try:
                        await msg.clear_reactions()
                    except Exception:
                        pass

                    await role.delete(reason="Removed toggleable role")
                except discord.Forbidden:
                    await msg.edit("I cannot delete this role")


    @checks.is_staff_or_perms("Mod", manage_roles=True)
    @commands.guild_only()
    @commands.command()
    async def addtogglerole(self, ctx, emoji: str, keyword: str, role: typing.Union[discord.Role, str], *,
                            description: str):
        """
        Adds a toggleable role (Mod+ only)
        - Emoji, the emote displayed when listing (if you do not want an emoji, type 'none' or 'noemoji' for this argument
        - Keyword, phrase that is used to toggle this role with .togglerole
        - Role, The actual role that is being toggled, you may type it out (case is sensitive, use quotes for spaces) or use the role id. If the role does not exist, the bot will make it for you
        - Description, Phrase to tell people what the role is for.
        """
        sendfinalmsg = True
        if isinstance(role, str):
            res, msg = await paginator.YesNoMenu(f"Would you like to create a role called {escape_mentions(role)}?").prompt(ctx)
            if res:
                res, msg = await paginator.YesNoMenu("Ok, would you like to make it pingable?").prompt(ctx)
                try:
                    role = await ctx.guild.create_role(reason="New toggleable role", name=role, mentionable=res)
                    await msg.edit(content=f"New role created! Added role {escape_mentions(role.name)} under keyword {escape_mentions(keyword)} use `togglerole {escape_mentions(keyword)}` to apply or remove it")
                    sendfinalmsg = False
                except discord.Forbidden:
                    await msg.edit(content="Unable to create role due to lack of permissions!")
                    try:
                        await msg.clear_reactions()
                    except Exception:
                        pass
            else:
                try:
                    await msg.edit(content="Role not created")
                    await msg.clear_reactions()
                except Exception:
                    pass
                return


        if emoji.lower() in ('none', 'noemoji', 'No emoji'):
            emoji = None

        roledict = {
            'emoji': emoji,
            'roleid': role.id,
            'description': description
        }

        jsonroleobj = json.dumps(roledict)
        async with self.bot.db.acquire() as conn:
            if await conn.fetchval("SELECT roles FROM toggleroles WHERE guildid = $1", ctx.guild.id) is None:
                query = "UPDATE toggleroles SET roles = jsonb_build_object($1::TEXT, $2::jsonb) WHERE guildid = $3"
            else:
                query = "UPDATE toggleroles SET roles = roles::jsonb || jsonb_build_object($1::TEXT, $2::jsonb) WHERE guildid = $3"

            await conn.execute(query, keyword, jsonroleobj, ctx.guild.id)
            if sendfinalmsg:
                await ctx.send(f"Added toggleable role {escape_mentions(role.name)} under keyword {escape_mentions(keyword)} use `togglerole {escape_mentions(keyword)}` to apply or remove it")

    # util functions
    async def setupdbguild(self, guildid):
        """Adds a json config for a guild to store toggleable roles in"""
        async with self.bot.db.acquire() as conn:
            if await conn.fetchval("SELECT guildid FROM toggleroles WHERE guildid = $1", guildid) is None:
                await conn.execute("INSERT INTO toggleroles (guildid) VALUES ($1)", guildid)

    async def getrolesfromdb(self, guildid: int):
        """Gets a guild's saved toggleroles"""
        async with self.bot.db.acquire() as conn:
            return await conn.fetchval("SELECT roles FROM toggleroles WHERE guildid = $1", guildid)

def setup(bot):
    bot.add_cog(ToggleRoles(bot))
