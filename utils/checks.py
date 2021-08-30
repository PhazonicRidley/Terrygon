import typing
import discord
from discord.ext import commands
from utils import errors


def has_role(user: discord.Member, role: discord.Role) -> bool:
    """Checks if a user has a role"""
    return role in user.roles


# adapted from https://git.catgirlsin.space/noirscape/kirigiri/src/branch/master/utils/mod_check.py#L88 under the GPL license
# adapted from https://github.com/Rapptz/discord.py/blob/d9a8ae9c78f5ca0eef5e1f033b4151ece4ed1028/discord/ext/commands/core.py#L1533
def is_staff_or_perms(min_staff_role: str, **perms):
    """Checks if a user has permission to use a command"""

    async def wrapper(ctx):
        if not ctx.guild:
            return False

        if ctx.author == ctx.guild.owner:
            return True

        # get global perms for the user
        permissions = ctx.author.guild_permissions
        missing = [perm for perm, value in perms.items() if getattr(permissions, perm, None) != value]

        # check for staff
        check_roles = ['mod', 'admin', 'owner']
        for role in check_roles.copy():
            if check_roles.index(role) < check_roles.index(min_staff_role.lower()):
                check_roles.remove(role)

        staff_roles = list(
            await ctx.bot.db.fetchrow("SELECT mod_role, admin_role, owner_role FROM roles WHERE guild_id = $1",
                                      ctx.guild.id))

        while len(check_roles) != len(staff_roles):
            try:
                del staff_roles[0]
            except IndexError as e:
                raise commands.CommandInvokeError(e)

        user_roles = [role.id for role in ctx.message.author.roles]
        if any(role in user_roles for role in staff_roles) or not missing or permissions.administrator:
            return True
        else:
            raise errors.MissingStaffRoleOrPerms(min_staff_role, missing)

    return commands.check(wrapper)


# TODO: look into running checks as non decorators. If not possible, merge this and the deco together under one function.
async def nondeco_is_staff_or_perms(target, db, min_staff_role, **perms) -> bool:
    if not target or not target.guild:
        return False

    # get global perms for the user
    if isinstance(target.author, discord.Member):
        permissions = target.author.guild_permissions
        missing = []
        if not perms:
            missing = ['no perms given']
        else:
            missing = [perm for perm, value in perms.items() if getattr(permissions, perm, None) != value]

    else:
        missing = ['no perms given']
        permissions = discord.Permissions(administrator=False)
    # check for staff
    check_roles = ['mod', 'admin', 'owner']
    for role in check_roles.copy():
        if check_roles.index(role) < check_roles.index(min_staff_role.lower()):
            check_roles.remove(role)
    res = await db.fetchrow("SELECT mod_role, admin_role, owner_role FROM roles WHERE guild_id = $1", target.guild.id)
    if not res:
        return False
    staff_roles = list(res)

    while len(check_roles) != len(staff_roles):
        try:
            del staff_roles[0]
        except IndexError as e:
            raise commands.CommandInvokeError(e)

    if isinstance(target, commands.Context):
        user_roles = [role.id for role in target.message.author.roles]
    elif isinstance(target, discord.Message):
        user_roles = [role.id for role in target.author.roles]
    else:
        raise commands.BadArgument(message="Bad argument passed")
    if any(role in user_roles for role in staff_roles) or not missing or permissions.administrator:
        return True
    else:
        return False


def is_trusted_or_perms(**perms):
    async def wrapper(ctx):
        if not ctx.guild:
            return False

        if await nondeco_is_staff_or_perms(ctx, ctx.bot.db, 'Mod', **perms):
            return True

        async with ctx.bot.db.acquire() as conn:
            trusted_users = await conn.fetchval("SELECT trusted_uid FROM trusted_users WHERE guild_id = $1",
                                                ctx.guild.id)
            if trusted_users and ctx.author.id in trusted_users:
                return True
            else:
                raise errors.UntrustedError()

    return commands.check(wrapper)


def is_bot_owner():
    async def wrapper(ctx):
        if await ctx.bot.is_owner(ctx.author):
            return True
        else:
            raise errors.BotOwnerError()

    return commands.check(wrapper)


async def mod_bot_protection(bot, ctx: commands.Context,
                             target: typing.Union[discord.Member, discord.TextChannel, discord.User, discord.Guild],
                             action: str) -> str or None:
    # check if valid user
    if isinstance(target, discord.User):
        return None
    owner_role = ctx.guild.get_role(
        (await bot.db.fetchval("SELECT owner_role FROM roles WHERE guild_id = $1", ctx.guild.id)))
    admin_role = ctx.guild.get_role(
        (await bot.db.fetchval("SELECT admin_role FROM roles WHERE guild_id = $1", ctx.guild.id)))
    mod_role = ctx.guild.get_role(
        (await bot.db.fetchval("SELECT mod_role FROM roles WHERE guild_id = $1", ctx.guild.id)))
    staff_roles = (admin_role, mod_role)

    if target == ctx.author:
        return f"You cannot {action} yourself"

    elif target == ctx.bot.user:
        return f"You cannot {action} me"

    elif owner_role in target.roles or target == target.guild.owner:
        return f"You cannot {action} an owner"

    elif any(role in staff_roles for role in target.roles) and owner_role not in ctx.author.roles:
        return f"Cannot {action} a staff member unless you are an owner!"

    else:
        return None
