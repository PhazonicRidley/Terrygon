import re
import random
import discord


# credit https://github.com/nh-server/Kurisu/blob/port/utils/utils.py#L30

def gen_color(seed):
    random.seed(seed)
    c_r = random.randint(0, 255)
    c_g = random.randint(0, 255)
    c_b = random.randint(0, 255)
    return discord.Color((c_r << 16) + (c_g << 8) + c_b)


def parse_time(time_string) -> int:
    """Parses a time string in dhms format to seconds"""
    units = {
        "d": 86400,
        "h": 3600,
        "m": 60,
        "s": 1
    }
    seconds = 0
    match = re.findall("([0-9]+[smhd])", time_string)  # Thanks to 3dshax server's former bot
    if not match:
        return -1
    for item in match:
        seconds += int(item[:-1]) * units[item[-1]]
    return seconds


async def getStaffRoles(ctx) -> list:
    """Get's a guild's staff roles"""
    async with ctx.bot.db.acquire() as conn:
        ids = await conn.fetchrow("SELECT modrole, adminrole, ownerrole FROM roles WHERE guildid = $1",
                                  ctx.guild.id)
        staffroles = []
        for id in ids:
            staffroles.append(ctx.guild.get_role(id))
        while None in staffroles:
            staffroles.remove(None)

    return staffroles


async def checkIfPrivateChannel(ctx, channel: discord.TextChannel):
    """Checks if a channel is private"""
    roles = []
    if await ctx.bot.db.fetchval("SELECT approvalSystem FROM guild_settings WHERE guildid = $1", ctx.guild.id):

        roles.append(ctx.guild.get_role(
            await ctx.bot.db.fetchval("SELECT approvedrole FROM roles WHERE guildid = $1", ctx.guild.id)))
        while None in roles:
            roles.remove(None)

    roles.append(ctx.guild.default_role)
    for r in roles:
        if channel.overwrites_for(r).read_messages is False:
            return True

    return False
