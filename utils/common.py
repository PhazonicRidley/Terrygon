import re
import random
import discord
import io
from PIL import Image
import webcolors
from discord.ext import commands


# credit https://github.com/nh-server/Kurisu/blob/port/utils/utils.py#L30
def gen_color(seed: int) -> discord.Color:
    random.seed(seed)
    c_r = random.randint(0, 255)
    c_g = random.randint(0, 255)
    c_b = random.randint(0, 255)
    return discord.Color((c_r << 16) + (c_g << 8) + c_b)


def parse_time(time_string: str) -> int:
    """Parses a time string in dhms format to seconds"""
    units = {
        "d": 86400,
        "h": 3600,
        "m": 60,
        "s": 1
    }
    seconds = 0
    match = re.findall(r"([0-9]+[smhd])", time_string)  # Thanks to 3dshax server's former bot
    if not match:
        return -1
    for item in match:
        seconds += int(item[:-1]) * units[item[-1]]
    return seconds


async def get_staff_roles(ctx: commands.Context) -> list:
    """Get's a guild's staff roles"""
    async with ctx.bot.db.acquire() as conn:
        ids = await conn.fetchrow("SELECT mod_role, admin_role, owner_role FROM roles WHERE guild_id = $1",
                                  ctx.guild.id)
        staff_roles = []
        for id in ids:
            staff_roles.append(ctx.guild.get_role(id))
        while None in staff_roles:
            staff_roles.remove(None)

    return staff_roles


async def check_private_channel(ctx: commands.Context, channel: discord.TextChannel) -> bool:
    """Checks if a channel is private"""
    roles = []
    if await ctx.bot.db.fetchval("SELECT approval_system FROM guild_settings WHERE guild_id = $1", ctx.guild.id):

        roles.append(ctx.guild.get_role(
            await ctx.bot.db.fetchval("SELECT approved_role FROM roles WHERE guild_id = $1", ctx.guild.id)))
        while None in roles:
            roles.remove(None)

    roles.append(ctx.guild.default_role)
    for r in roles:
        if channel.overwrites_for(r).read_messages is False:
            return True

    return False


def hex_to_color(color_hex: str) -> (discord.Color, str) or None:
    """Makes sure a hex is good, returns a discord.Color object from the hex."""
    # first make sure the hex is valid.
    if color_hex[0] != '#':
        color_hex = '#' + color_hex
    if len(color_hex) != 7:
        return None
    try:
        rgb_triple = webcolors.hex_to_rgb(color_hex)
    except ValueError:
        return None

    return discord.Color.from_rgb(*rgb_triple), color_hex


def image_from_rgb(rgb_triple: (int, int, int)) -> discord.File:
    """Gets a color image"""
    color_img = Image.new("RGB", (500, 500), rgb_triple)
    attachment = io.BytesIO()
    color_img.save(attachment, 'PNG')
    attachment.seek(0)
    d_file = discord.File(attachment, filename="color.png")
    return d_file


def parse_rgb(input_str: str) -> tuple or None:
    """Parses a string into rgb"""
    input_str = input_str.replace(" ", "")
    rgb_triple = input_str.split(",")
    if len(rgb_triple) != 3:
        return None
    color = []
    for rgb in rgb_triple:
        if not rgb.isnumeric():
            return None
        elif int(rgb) < 0 or int(rgb) > 255:
            return None
        else:
            color.append(int(rgb))

    return tuple(color)


def convert_c_to_f(celsius: int) -> int:
    """Converts celsius to fahrenheit"""
    return round((celsius * 9 / 5) + 32)
