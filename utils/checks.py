import discord
from discord.ext import commands
import yaml
import sys
from utils import errors


def hasRole(user: discord.Member, role: discord.Role) -> bool:
    return role in user.roles


def readConfig(config) -> str:
    try:
        with open("config.yml", "r") as f:
            loadedYml = yaml.safe_load(f)
            return loadedYml[config]
    except FileNotFoundError:
        print("Cannot find config.yml. Does it exist?")
        sys.exit(1)


# adapted from https://git.catgirlsin.space/noirscape/kirigiri/src/branch/master/utils/mod_check.py#L88 under the GPL license
# adapted from https://github.com/Rapptz/discord.py/blob/d9a8ae9c78f5ca0eef5e1f033b4151ece4ed1028/discord/ext/commands/core.py#L1533

def is_staff_or_perms(minStaffRole: str, **perms):
    async def wrapper(ctx):
        if ctx.message.author == ctx.guild.owner:
            return True

        # get global perms for the user
        permissions = ctx.author.guild_permissions
        missing = [perm for perm, value in perms.items() if getattr(permissions, perm, None) != value]

        # check for staff
        checkroles = ['mod', 'admin', 'owner']
        for role in checkroles.copy():
            if checkroles.index(role) < checkroles.index(minStaffRole.lower()):
                checkroles.remove(role)

        staffroles = list(
            await ctx.bot.db.fetchrow("SELECT modRole, adminRole, ownerRole FROM roles WHERE guildID = $1",
                                      ctx.message.guild.id))

        while len(checkroles) != len(staffroles):
            try:
                del staffroles[0]
            except IndexError as e:
                raise commands.CommandInvokeError(e)

        userRoles = [role.id for role in ctx.message.author.roles]
        if any(role in userRoles for role in staffroles) or not missing or permissions.administrator:
            return True
        else:
            raise errors.missingStaffRoleOrPerms(minStaffRole, missing)

    return commands.check(wrapper)


async def nondeco_is_staff_or_perms(ctx, minStaffRole, **perms) -> bool:
    if ctx.message.author == ctx.guild.owner:
        return True

    # get global perms for the user
    permissions = ctx.author.guild_permissions
    missing = []
    if not perms:
        missing = ['no perms given']
    else:
        missing = [perm for perm, value in perms.items() if getattr(permissions, perm, None) != value]

    # check for staff
    checkroles = ['mod', 'admin', 'owner']
    for role in checkroles.copy():
        if checkroles.index(role) < checkroles.index(minStaffRole.lower()):
            checkroles.remove(role)

    staffroles = list(
        await ctx.bot.db.fetchrow("SELECT modRole, adminRole, ownerRole FROM roles WHERE guildID = $1",
                                  ctx.message.guild.id))

    while len(checkroles) != len(staffroles):
        try:
            del staffroles[0]
        except IndexError as e:
            raise commands.CommandInvokeError(e)

    userRoles = [role.id for role in ctx.message.author.roles]
    if any(role in userRoles for role in staffroles) or not missing or permissions.administrator:
        return True
    else:
        return False


def is_trusted_or_perms(**perms):
    async def wrapper(ctx):
        if await nondeco_is_staff_or_perms(ctx, 'Mod', **perms):
            return True

        async with ctx.bot.db.acquire() as conn:
            trustedusers = await conn.fetchval("SELECT trusteduid FROM trustedusers WHERE guildid = $1", ctx.guild.id)
            if trustedusers and ctx.author.id in trustedusers:
                return True
            else:
                raise errors.untrustedError()

    return commands.check(wrapper)


def is_bot_owner():
    async def wrapper(ctx):
        botOwners = readConfig("botOwners")
        if ctx.author.id in botOwners:
            return True
        else:
            raise errors.botOwnerError()

    return commands.check(wrapper)


async def modAndBotProtection(bot, ctx, target, action):
    owner_role = ctx.guild.get_role(
        (await bot.db.fetchval("SELECT ownerRole FROM roles WHERE guildID = $1", ctx.guild.id)))
    # staff_role = ctx.guild.get_role((await bot.db.fetchrow("SELECT staffRole FROM roles WHERE guildID = $1", ctx.guild.id)))
    admin_role = ctx.guild.get_role(
        (await bot.db.fetchval("SELECT adminRole FROM roles WHERE guildID = $1", ctx.guild.id)))
    mod_role = ctx.guild.get_role((await bot.db.fetchval("SELECT modRole FROM roles WHERE guildID = $1", ctx.guild.id)))
    staff_roles = (admin_role, mod_role)

    if target == ctx.message.author:
        return f"You cannot {action} yourself"

    elif target.bot:
        return f"You cannot {action} bots"

    elif owner_role in target.roles:
        return f"You cannot {action} an owner"

    elif any(role in staff_roles for role in target.roles) and owner_role not in ctx.author.roles:
        return f"Cannot {action} a staff member unless you are an owner!"

    else:
        return None
