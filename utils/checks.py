import discord
from discord.ext import commands
from main import read_config
from utils import errors


def has_role(user: discord.Member, role: discord.Role) -> bool:
    return role in user.roles


# adapted from https://git.catgirlsin.space/noirscape/kirigiri/src/branch/master/utils/mod_check.py#L88 under the GPL license
# adapted from https://github.com/Rapptz/discord.py/blob/d9a8ae9c78f5ca0eef5e1f033b4151ece4ed1028/discord/ext/commands/core.py#L1533
def is_staff_or_perms(min_staff_role: str, **perms):
    """Checks if a user has permission to use a command"""
    async def wrapper(ctx):
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

        staff_roles = list(await ctx.bot.db.fetchrow("SELECT modRole, adminRole, ownerRole FROM roles WHERE guildID = $1", ctx.guild.id))

        while len(check_roles) != len(staff_roles):
            try:
                del staff_roles[0]
            except IndexError as e:
                raise commands.CommandInvokeError(e)

        user_roles = [role.id for role in ctx.message.author.roles]
        if any(role in user_roles for role in staff_roles) or not missing or permissions.administrator:
            return True
        else:
            raise errors.missingStaffRoleOrPerms(min_staff_role, missing)

    return commands.check(wrapper)


async def nondeco_is_staff_or_perms(target, db, min_staff_role, **perms) -> bool:
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

    staff_roles = list(await db.fetchrow("SELECT modRole, adminRole, ownerRole FROM roles WHERE guildID = $1", target.guild.id))

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
        if await nondeco_is_staff_or_perms(ctx, ctx.bot.db, 'Mod', **perms):
            return True
        
        async with ctx.bot.db.acquire() as conn:
            trusted_users = await conn.fetchval("SELECT trusteduid FROM trustedusers WHERE guildid = $1", ctx.guild.id)
            if trusted_users and ctx.author.id in trusted_users:
                return True
            else:
                raise errors.untrustedError()

    return commands.check(wrapper)


def is_bot_owner():
    async def wrapper(ctx):
        bot_owners = read_config("botOwners")
        if ctx.author.id in bot_owners:
            return True
        else:
            raise errors.botOwnerError()

    return commands.check(wrapper)


async def mod_bot_protection(bot, ctx, target, action):
    owner_role = ctx.guild.get_role((await bot.db.fetchval("SELECT ownerRole FROM roles WHERE guildID = $1", ctx.guild.id)))
    admin_role = ctx.guild.get_role((await bot.db.fetchval("SELECT adminRole FROM roles WHERE guildID = $1", ctx.guild.id)))
    mod_role = ctx.guild.get_role((await bot.db.fetchval("SELECT modRole FROM roles WHERE guildID = $1", ctx.guild.id)))
    staff_roles = (admin_role, mod_role)

    if target == ctx.author:
        return f"You cannot {action} yourself"

    elif target.bot:
        return f"You cannot {action} bots"

    elif owner_role in target.roles or target == target.guild.owner:
        return f"You cannot {action} an owner"

    elif any(role in staff_roles for role in target.roles) and owner_role not in ctx.author.roles:
        return f"Cannot {action} a staff member unless you are an owner!"

    else:
        return None
