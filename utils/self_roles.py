import typing
import discord
import webcolors
from discord.ext import commands
from PIL import Image
import io
from utils import paginator, common


# collection of functions to assist with managing self roles


def check_tables(*tables):
    """Makes sure a table is valid"""

    def decorator(func):
        def wrapper(*args, **kwargs):
            func_arg_names = [x.lower() for x in func.__code__.co_varnames]
            if not 'table' in func_arg_names:
                raise AttributeError("No table given.")
            table = args[func_arg_names.index("table")]
            if table not in tables:
                raise AttributeError("Invalid table given ")
            return func(*args, **kwargs)

        return wrapper

    return decorator


@check_tables('toggle_roles', 'communal_colors')
async def check_existing_keyword_roles(ctx: commands.Context, table: str, keyword: str) -> int:
    role_id = await ctx.bot.db.fetchval(f"SELECT role_id FROM {table} WHERE guild_id = $1 AND keyword = $2",
                                        ctx.guild.id, keyword)
    existing_role = ctx.guild.get_role(role_id)
    if role_id:
        res, msg = paginator.YesNoMenu(
            "Keyword already bound to a word, would you like to replace the role this keyword is bound to?")
        if res:
            await msg.edit(content="Replacing role.")
            await ctx.bot.db.execute(f"DELETE FROM {table} WHERE role_id = $1 AND guild_id = $2", role_id, ctx.guild.id)
            if existing_role:
                del_res, del_msg = await paginator.YesNoMenu("Would you like to delete the old role?").prompt(ctx)
                if del_res:
                    await del_msg.edit(content="Deleting role")
                    try:
                        await existing_role.delete()
                    except discord.Forbidden:
                        pass
                else:
                    await del_msg.edit(content="Role not deleted.")
        else:
            await msg.edit("Role not being replaced, quitting.")
            return -1
    return 0


@check_tables('toggle_roles', 'communal_colors', 'personal_colors')
async def add_self_role(ctx: commands.Context, table: str, role: typing.Union[discord.Role, str], **kwargs):
    """Adds a self role to the database."""
    db = ctx.bot.db
    if isinstance(role, str):
        res, msg = await paginator.YesNoMenu("No role by this name, would you like to make a new one?").prompt(ctx)
        if res:
            try:
                role = await ctx.guild.create_role(name=role, reason=f"{table.replace('_', ' ')[:-1].title()} created.")
                if kwargs.get('color_hex'):
                    await role.edit(color=discord.Color.from_rgb(*webcolors.hex_to_rgb(kwargs['color_hex'])))
            except discord.Forbidden:
                return await msg.edit(content="I cannot manage roles.")
            await msg.edit(content=f"New role {role.name} created.")
        else:
            return await msg.edit("Role not created.")

    kwargs['role_id'] = role.id
    kwargs['guild_id'] = ctx.guild.id
    # add to database
    no_of_columns = await db.fetchval("SELECT COUNT(*) FROM information_schema.columns WHERE table_name=$1", table)
    place_holders = ""
    for i in range(1, no_of_columns + 1):
        place_holders += f"${i}, "
    place_holders = place_holders[:-2]
    query = f"INSERT INTO {table} ({', '.join(kwargs.keys())}) VALUES ({place_holders})"
    await db.execute(query, *kwargs.values())


@check_tables('toggle_roles', 'communal_colors', 'personal_colors')
async def delete_self_role(ctx: commands.Context, table: str, token: tuple) -> int:
    """Removes a self role"""
    # token can either be the keyword or user id
    db = ctx.bot.db
    # get role
    role_id = await db.fetchval(f"SELECT role_id FROM {table} WHERE guild_id = $1 AND {token[0]} = $2", ctx.guild.id,
                                token[1])
    if not role_id:
        await ctx.send(f"{table.replace('_', ' ')[:-1].title()} does not exist.")
        return -1
    role = ctx.guild.get_role(role_id)
    if role:
        res, msg = await paginator.YesNoMenu(f"Would you like to delete the {role} role?").prompt(ctx)
        if res:
            try:
                await role.delete(reason=f"Removing {table.replace('_', ' ')[:-1].title()}")
                await msg.edit(content="Role deleted.")
            except discord.Forbidden:
                await msg.edit(content="Role couldn't be deleted due to lack of permissions.")
        else:
            await msg.edit(content="Role not deleted.")
    await db.execute(f"DELETE FROM {table} WHERE {token[0]} = $1 AND guild_id = $2", token[1], ctx.guild.id)
    return 0


@check_tables('toggle_roles', 'communal_colors')
async def list_all_roles(ctx: commands.Context, table: str):
    """Gets an embed for toggleable roles and communal color roles."""
    # get db data
    db = ctx.bot.db
    data = await db.fetch(f"SELECT * FROM {table} WHERE guild_id = $1", ctx.guild.id)
    if not data:
        return await ctx.send("No roles set to be listed.")
    embed = discord.Embed(color=common.gen_color(ctx.guild.id))
    if table.lower() == "toggle_roles":
        embed.title = f"Toggleable roles for {ctx.guild.name}"
        role_str_list = []
        deleted_roles = ""
        for toggle_role in data:
            role = ctx.guild.get_role(toggle_role['role_id'])
            if role:
                role_str_list.append(
                    f"- {toggle_role['emoji'] if toggle_role['emoji'] else ''} **Keyword:** `{toggle_role['keyword']}`, **Role:** `{role.name}`\n")
            else:
                deleted_roles += f"- **Keyword:** {toggle_role['keyword']}\n"

    else:
        embed.title = f"Communal Color roles for {ctx.guild.name}"
        role_str_list = []
        deleted_roles = ""
        for toggle_role in data:
            role = ctx.guild.get_role(toggle_role['role_id'])
            if role:
                role_str_list.append(
                    f"- **Color Hex:** {toggle_role['color_hex']}, **Keyword:** {toggle_role['keyword']}\n")
            else:
                deleted_roles += f"- **Keyword:** {toggle_role['keyword']}\n"

    if deleted_roles:
        embed.add_field(name=":warning: **Deleted roles detected, please delete these roles!**", value=deleted_roles)

    pages = paginator.ReactDeletePages(paginator.BasicEmbedMenu(role_str_list, per_page=8, embed=embed),
                                       clear_reactions_after=True, check_embeds=True)
    await pages.start(ctx)


# inspired from fakebot by Such Meme, Many Skill.
@check_tables('toggle_roles', 'communal_colors', 'personal_colors')
async def get_role_info(ctx: commands.Context, table: str, token: tuple) -> int:
    """Gets info on a self role"""
    # get role
    db_data = await ctx.bot.db.fetchrow(f"SELECT * FROM {table} WHERE guild_id = $1 AND {token[0]} = $2", ctx.guild.id,
                                        token[1])
    if not db_data:
        await ctx.send(f"No self role for `{token[1]}` found!")
        return -1
    role = ctx.guild.get_role(db_data['role_id'])
    if not role:
        await ctx.send("Role has been deleted, please remove it from the bot.")
        return -1

    embed = discord.Embed(title=f"{table.replace('_', ' ')[:-1].title()} {role.name}",
                          description="Information about self role.", color=role.color)
    role_data = dict(db_data).copy()
    del role_data['guild_id']
    del role_data['role_id']
    if role_data.get('user_id'):
        user = ctx.guild.get_member(role_data['user_id'])
        if not user:
            await ctx.send("User doesn't exist.")
            return -1
        del role_data['user_id']
        role_data['user'] = user
    role_data['role'] = role
    if role_data.get("description"):
        # moves description to the end of the dictionary so it can be the final field
        role_data['description'] = role_data.pop("description")
    for field, data in role_data.items():
        embed.add_field(name=field.replace("_", " ").title(), value=data, inline=False)

    file = None
    if table[-6:].lower() == "colors":
        role_rgb = role.color.to_rgb()
        file = common.image_from_rgb(role_rgb)
        embed.set_image(url="attachment://color.png")

    await ctx.send(embed=embed, file=file)


@check_tables('toggle_roles', 'communal_colors', 'personal_colors')
async def delete_all_roles(ctx: commands.Context, table: str):
    """Deletes all self roles from a given guild."""
    res, msg = await paginator.YesNoMenu(f"Would you like to remove all {table.replace('_', ' ').title()}?").prompt(ctx)
    if res:
        role_ids = [data['role_id'] for data in
                    await ctx.bot.db.fetch(f"SELECT role_id FROM {table} WHERE guild_id = $1", ctx.guild.id)]
        if not role_ids:
            await msg.edit(content="No roles saved")
            return
        roles = [ctx.guild.get_role(r_id) for r_id in role_ids if ctx.guild.get_role(r_id)]
        for role in roles:
            try:
                await role.delete(reason=f"Removing all {table.replace('_', ' ').title()}")
            except discord.Forbidden:
                await msg.edit(
                    content=f"I cannot manage roles or the role I am trying to delete is above my role (Current role {role.name}) .")
                return
        await ctx.bot.db.execute(f"DELETE FROM {table} WHERE guild_id = $1", ctx.guild.id)
        await msg.edit(content=f"All {table.replace('_', ' ').title()} deleted.")
    else:
        await msg.edit(content="Quitting.")
