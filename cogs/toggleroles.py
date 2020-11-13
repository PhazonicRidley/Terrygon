import discord
from discord.ext import commands, flags
from discord.utils import escape_mentions
import json
import typing
import io
from utils import checks, paginator


class ToggleRoles(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    # temporary, clean up later
    async def cog_before_invoke(self, ctx):
        await self.setup_db_guild(ctx.guild.id)

    @commands.guild_only()
    @commands.command(name="togglerole")
    async def toggle_role(self, ctx, keyword: str = None):
        """Toggle a role! provide no argument if you wish to see the list"""
        if keyword is None:
            return await self.list_roles(ctx)

        async with self.bot.db.acquire() as conn:
            json_role_entry = await conn.fetchval("SELECT roles->>$1 FROM toggleroles WHERE guildid = $2", keyword,
                                                  ctx.guild.id)
            if json_role_entry is None:
                return await ctx.send("This keyword doesn't match any saved roles. Did you spell it right?")

            role_id = json.loads(json_role_entry)['roleid']

            role = ctx.guild.get_role(role_id)
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

    async def list_roles(self, ctx):
        """Lists a guild's toggleable roles"""
        roles = await self.get_roles_from_db(ctx.guild.id)
        if not roles:
            return await ctx.send("No toggleable roles found, add some with `addtogglerole`")
        embed = discord.Embed(title=f"Toggleable roles for {ctx.guild.name}", colour=ctx.author.color.value)
        role_info_list = []
        deleted_role = False
        del_role_str = ""  # just make sure we dont get unbound errors
        for keyword, role_data in roles.items():
            role_data = json.loads(role_data)
            emoji = '' if role_data['emoji'] is None else str(role_data['emoji'])
            role = ctx.guild.get_role(role_data['roleid'])
            if not role:
                deleted_role = True
                del_role_str = f"- :warning: `{escape_mentions(keyword)}` has been deleted!\n"
                continue

            role_info_list.append(
                f"- {emoji} **__Role:__** {role.name} **__Description:__** {role_data['description']} **__Keyword:__** `{keyword}`\n")

        if deleted_role:
            del_role_str += "\nPlease update these roles with `addtogglerole` or deleted them with `deltogglerole`"
            if len(del_role_str) >= 1250:
                embed.add_field("**Deleted Toggle roles!**",
                                value="You have deleted toggle roles, see this text file on which ones they are")
                await ctx.send(file=discord.File(io.StringIO(del_role_str), filename='deleted-toggleroles.txt'))
            else:
                embed.add_field(name="**Deleted toggle roles!**",
                                value=del_role_str)

        pages = paginator.ReactDeletePages(paginator.BasicEmbedMenu(role_info_list, per_page=8, embed=embed),
                                           clear_reactions_after=True, check_embeds=True)
        await pages.start(ctx)

    @commands.guild_only()
    @checks.is_staff_or_perms("Mod", manage_roles=True)
    @commands.command(name="deltogglerole")
    async def del_toggle_role(self, ctx, keyword: str):
        """Removes a toggleable role from the database (Mod+ only)"""
        async with self.bot.db.acquire() as conn:

            if await conn.fetchval("SELECT roles->>$1 FROM toggleroles WHERE guildid = $2", keyword,
                                   ctx.guild.id) is None:
                return await ctx.send("Role does not exist in database for this server!")
            else:
                role_id = (json.loads(
                    await conn.fetchval("SELECT roles->>$1 FROM toggleroles WHERE guildid = $2", keyword,
                                        ctx.guild.id)))['roleid']
                role = ctx.guild.get_role(role_id)
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

    @commands.guild_only()
    @checks.is_staff_or_perms("Mod", manage_roles=True)
    @commands.command(name="addtogglerole")
    async def add_toggle_role(self, ctx, emoji: str, keyword: str, role: typing.Union[discord.Role, str], *,
                              description: str):
        """
        Adds a toggleable role (Mod+ only)
        - Emoji, the emote displayed when listing (if you do not want an emoji, type 'none' or 'noemoji' for this argument
        - Keyword, phrase that is used to toggle this role with [p]togglerole
        - Role, The actual role that is being toggled, you may type it out (case is sensitive, use quotes for spaces) or use the role id. If the role does not exist, the bot will make it for you
        - Description, Phrase to tell people what the role is for.
        """
        send_final_msg = True
        if isinstance(role, str):
            res, msg = await paginator.YesNoMenu(
                f"Would you like to create a role called {escape_mentions(role)}?").prompt(ctx)
            if res:
                res, msg = await paginator.YesNoMenu("Ok, would you like to make it pingable?").prompt(ctx)
                try:
                    role = await ctx.guild.create_role(reason="New toggleable role", name=role, mentionable=res)
                    await msg.edit(
                        content=f"New role created! Added role {escape_mentions(role.name)} under keyword {escape_mentions(keyword)} use `togglerole {escape_mentions(keyword)}` to apply or remove it")
                    send_final_msg = False
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

        role_dict = {
            'emoji': emoji,
            'roleid': role.id,
            'description': description
        }

        json_role_obj = json.dumps(role_dict)
        async with self.bot.db.acquire() as conn:
            if await conn.fetchval("SELECT roles FROM toggleroles WHERE guildid = $1", ctx.guild.id) is None:
                query = "UPDATE toggleroles SET roles = jsonb_build_object($1::TEXT, $2::jsonb) WHERE guildid = $3"
            else:
                query = "UPDATE toggleroles SET roles = roles::jsonb || jsonb_build_object($1::TEXT, $2::jsonb) WHERE guildid = $3"

            await conn.execute(query, keyword, json_role_obj, ctx.guild.id)
            if send_final_msg:
                await ctx.send(
                    f"Added toggleable role {escape_mentions(role.name)} under keyword {escape_mentions(keyword)} use `togglerole {escape_mentions(keyword)}` to apply or remove it")

    # util functions
    async def setup_db_guild(self, guild_id):
        """Adds a json config for a guild to store toggleable roles in"""
        async with self.bot.db.acquire() as conn:
            if await conn.fetchval("SELECT guildid FROM toggleroles WHERE guildid = $1", guild_id) is None:
                await conn.execute("INSERT INTO toggleroles (guildid) VALUES ($1)", guild_id)

    async def get_roles_from_db(self, guild_id: int):
        """Gets a guild's saved toggleroles"""
        async with self.bot.db.acquire() as conn:
            return await conn.fetchval("SELECT roles FROM toggleroles WHERE guildid = $1", guild_id)


def setup(bot):
    bot.add_cog(ToggleRoles(bot))
