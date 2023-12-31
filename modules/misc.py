from time import strftime
import discord
import webcolors
from discord.ext import commands
import re
import string
from terrygon import read_config
from utils import checks, common
from datetime import datetime, timedelta
import typing
import collections


class Reminder:

    def __init__(self, reminder_id, reminder, time_stamp):
        self.id = reminder_id
        self.reminder = reminder
        self.time_stamp = time_stamp


class Misc(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        self.curActivity = discord.Game(read_config("info", "activity"))
        self.curStatus = discord.Status.online

    @commands.guild_only()
    @commands.command(aliases=['mc'])
    async def membercount(self, ctx: commands.Context):
        """Prints member count"""
        bots = 0
        for member in ctx.guild.members:
            if member.bot:
                bots += 1

        await ctx.send(f"{ctx.guild.name} has {ctx.guild.member_count - bots} members and {bots} bots")

    @commands.guild_only()
    @commands.command(aliases=['currentperms'])
    async def currentpermissions(self, ctx: commands.Context, item: typing.Union[discord.Member, discord.Role] = None):
        """Lists a user's or a role's current permissions"""
        if item is None:
            item = ctx.author

        perm_names = []
        embed = discord.Embed(title=f"Permissions on {ctx.guild.name} for {type(item).__name__.lower()} {item.name}",
                              colour=item.color.value)
        perm_list = item.guild_permissions if isinstance(item, discord.Member) else item.permissions
        for name, value in perm_list:
            name = name.replace('_', ' ').title()
            if value:
                perm_names.append(name)

        if isinstance(item, discord.Member):
            highest_role_str = f"The highest role for {item}, {item.top_role.name}, is in position {item.top_role.position} out of {len(ctx.guild.roles) - 1}"

        else:
            highest_role_str = f"This role is in position {item.position} out of {len(ctx.guild.roles) - 1}"

        embed.add_field(name=f"Permission value: {perm_list.value}", value=", ".join(perm_names), inline=False)
        embed.add_field(name="Highest role location", value=highest_role_str, inline=False)
        await ctx.send(embed=embed)

    @commands.command()
    async def ping(self, ctx: commands.Context):
        """Pong!"""
        return await ctx.send(f":ping_pong:! Pong! Response time: {round(self.bot.latency * 1000, 2)} ms")

    @commands.command(aliases=['ui', 'onion'])
    async def userinfo(self, ctx: commands.Context, member: typing.Union[discord.Member, int, str] = None):
        """Prints userinfo on a member"""
        in_server = None
        if member is None:
            user = ctx.author
            in_server = True
        elif isinstance(member, int):
            try:
                user = await self.bot.fetch_user(member)
                in_server = False
            except discord.NotFound:
                return await ctx.send("💢 I cannot find that user")
        elif isinstance(member, discord.Member):
            user = member
            in_server = True
        elif isinstance(member, str):
            return await ctx.send("💢 I cannot find that user")

        if in_server:
            embed = discord.Embed(title=f'**Userinfo for {user.name}#{str(user.discriminator)}**',
                                  color=user.color.value)
            embed.description = f"""**User's ID:** {str(user.id)} \n **Join date:** {str(user.joined_at)} \n**Created on** {str(user.created_at)}\n **Current Status:** {str(user.status).upper() if str(user.status).lower() == "dnd" else str(user.status).title()}\n **User Activity:**: {str(user.activity)} \n **Default Profile Picture:** {str(user.default_avatar).title()}\n **Current Display Name:** {user.display_name}\n**Nitro Boost Date:** {str(user.premium_since)}\n **Current Top Role:** {str(user.top_role)}\n **Bot** {user.bot}\n **Color:** {str(hex(user.color.value)[2:]).zfill(6)}"""
            embed.set_thumbnail(url=user.avatar.url)
            await ctx.send(embed=embed)

        elif not in_server:
            try:
                ban = await ctx.guild.fetch_ban(user)
            except discord.NotFound:
                ban = None

            embed = discord.Embed(title=f'**Userinfo for {user.name}#{str(user.discriminator)}**',
                                  color=common.gen_color(user.id))
            embed.description = f"**User's ID:** {str(user.id)} \n **Default Profile Picture:** {str(user.default_avatar)} \n  **Created on:** {str(user.created_at)}\n **Bot:** {user.bot}\n {f'**Banned, reason:** {ban.reason}' if ban is not None else ''}"
            embed.set_footer(text=f'{user.name}#{user.discriminator} is not in your server.')
            embed.set_thumbnail(url=user.avatar.url)
            await ctx.send(embed=embed)

    @commands.command(aliases=['avi'])
    async def avatar(self, ctx: commands.Context, member: typing.Union[discord.Member, int, str] = None):
        """Gets a user's avatar"""
        in_server = None
        if member is None:
            user = ctx.author
            in_server = True
        elif isinstance(member, int):
            try:
                user = await self.bot.fetch_user(member)
                in_server = False
            except discord.NotFound:
                return await ctx.send("💢 I cannot find that user")
        elif isinstance(member, discord.Member):
            user = member
            in_server = True
        elif isinstance(member, str):
            await ctx.send("💢 I cannot find that user")
            return

        embed = discord.Embed(title=f"Avatar for {user.name}#{user.discriminator}",
                              color=user.color.value if in_server else common.gen_color(user.id))
        embed.set_image(url=user.avatar.url)
        await ctx.send(embed=embed)

    @commands.command()
    async def about(self, ctx: commands.Context):
        """Info about the bot"""
        await ctx.send("https://gitlab.com/PhazonicRidley/terrygon")

    @checks.is_bot_owner()
    @commands.command()
    async def invite(self, ctx: commands.Context):
        """DMs you a bot invite."""
        await ctx.author.send(f"https://discord.com/api/oauth2/authorize?client_id={ctx.me.id}&permissions=8&scope=bot")

    @commands.command(aliases=['spoiler'])
    async def spoil(self, ctx: commands.Context):
        """Returns image spoilered"""
        message = ctx.message
        msg_content = message.content[len(ctx.prefix) + len(ctx.command.name) + 1:]
        msg_content = msg_content.lstrip('r ')

        file_list: typing.List[discord.File] = []
        for attachment in message.attachments:
            file_list.append(await attachment.to_file(spoiler=True))

        try:
            await message.delete()
        except discord.Forbidden:
            pass

        if len(file_list) > 10:
            return await ctx.send("Cannot attach more than 10 files!")

        if msg_content == "" or not msg_content:
            await ctx.send(f"{ctx.author}:", files=file_list)
        else:
            await ctx.send(f"{ctx.author}: ||{msg_content}||", files=file_list)

    @commands.guild_only()
    @commands.command(name="guildinfo", aliases=['serverinfo', 'server'])
    async def guild_info(self, ctx: commands.Context):
        """Posts guild info"""
        embed = discord.Embed(title=f"**Server info for: {ctx.guild.name}**", colour=common.gen_color(ctx.guild.id))
        if ctx.guild.icon:
            embed.set_thumbnail(url=ctx.guild.icon_url)

        approval_system = "enabled" if await self.bot.db.fetchval(
            "SELECT approval_system FROM guild_settings WHERE guild_id = $1", ctx.guild.id) else "disabled"

        embed.add_field(
            name="**Stats**",
            value=f":slight_smile: **__Number of emotes:__** {len(ctx.guild.emojis)}\n:soccer: **__Region__:** {str(ctx.guild.region).title()}\n:white_check_mark: **__Verification Level:__** {str(ctx.guild.verification_level).title()}\n{self.bot.terrygon_logger.emotes['creationdate']} **__Creation:__** {strftime(str(ctx.guild.created_at))}\n:eyes: **__Approval System:__** {approval_system.title()}\n{self.bot.terrygon_logger.emotes['id']} **__Guild ID:__** {ctx.guild.id}\n",
            inline=False
        )
        # adapted from https://gitlab.com/lightning-bot/Lightning/-/blob/v3/cogs/meta.py#L607
        # get member info
        memberStatusCollection = collections.Counter()
        for member in ctx.guild.members:
            if member.bot:
                memberStatusCollection['bot'] += 1
            else:
                memberStatusCollection[str(member.status)] += 1

        embed.add_field(name="**Member Info**",
                        value=f"<:online:720369347440410697> **__Online:__** {memberStatusCollection['online']}\n<:idle:720369314494021663> **__Idle:__** {memberStatusCollection['idle']}\n<:dnd:720369337109577739> **__Do not disturb:__** {memberStatusCollection['dnd']}\n<:offline:720369327915794552> **__Offline:__** {memberStatusCollection['offline']}\n:robot: **__Bots:__** {memberStatusCollection['bot']}\n:palms_up_together: **__Total:__** {ctx.guild.member_count}\n:crown: **__Owner:__** {ctx.guild.owner}",
                        inline=False)

        # get role info
        async with self.bot.db.acquire() as conn:
            mod_role = ctx.guild.get_role(
                await conn.fetchval("SELECT mod_role FROM roles WHERE guild_id = $1", ctx.guild.id))
            mod_role = "No Mod role set" if mod_role is None else mod_role

            admin_role = ctx.guild.get_role(
                await conn.fetchval("SELECT admin_role FROM roles WHERE guild_id = $1", ctx.guild.id))
            admin_role = "No Admin role set" if admin_role is None else admin_role

            owner_role = ctx.guild.get_role(
                await conn.fetchval("SELECT owner_role FROM roles WHERE guild_id = $1", ctx.guild.id))
            owner_role = "No Owner role set" if owner_role is None else owner_role

            muted_role = ctx.guild.get_role(
                await conn.fetchval("SELECT muted_role FROM roles WHERE guild_id = $1", ctx.guild.id))
            muted_role = "No Muted role set" if muted_role is None else muted_role
            if approval_system == 'enabled':
                approval_role = ctx.guild.get_role(
                    await conn.fetchval("SELECT approved_role FROM roles WHERE guild_id = $1", ctx.guild.id))
            else:
                approval_role = "Approval System Disabled"

        embed.add_field(name="**Role Info**",
                        value=f":shield: **__Number Of Roles:__** {len(ctx.guild.roles)}\n:helicopter: **__Mod Role:__** {mod_role}\n:hammer: **__Admin Role:__** {admin_role}\n:crown: **__Owner Role:__** {owner_role}\n:+1: **__Approval Role:__** {approval_role}\n:mute: **__Muted Role:__** {muted_role}",
                        inline=False)

        # channel info

        embed.add_field(name="**Channel Info**",
                        value=f":hash: **__Number of text channels:__** {len(ctx.guild.text_channels)}\n:loud_sound: **__Number of voice channels:__** {len(ctx.guild.voice_channels)}\n",
                        inline=False)

        await ctx.send(embed=embed)

    @checks.is_bot_owner()
    @commands.command()
    async def activity(self, ctx: commands.Context, *, msg: str = None):
        """Change the bots playing/watching/listening to activity (Bot Owners only)"""
        to = False
        if msg is None:
            await self.bot.change_presence()
            await ctx.send("Removing status")
            return

        if msg.split()[0].lower() == "watching":
            msg = msg[9:]
            act_type = discord.ActivityType.watching

        elif msg.split()[0].lower() == "listening":
            if msg.split()[1].lower() == 'to':
                to = True
            msg = msg[10:]
            act_type = discord.ActivityType.listening
        else:
            act_type = discord.ActivityType.playing
            msg = re.sub(r'^playing ', '', msg, flags=re.I)

        if to:
            msg = msg[3:]
            out = f"Setting current status to: `{str(act_type)[13:].title()} to {msg}" + '`'

        else:
            out = f"Setting current status to: `{str(act_type)[13:].title()} {msg}" + '`'

        self.curActivity = discord.Activity(name=msg, type=act_type)
        await self.bot.change_presence(status=self.curStatus, activity=self.curActivity)
        await ctx.send(out)

    @checks.is_bot_owner()
    @commands.command()
    async def status(self, ctx: commands.Context, new_status):
        """Changes the bots discord status, valid options are online, idle, dnd, or offline (Bot Owners only)"""
        new_status = new_status.lower()
        statuses = {
            'online': discord.Status.online,
            'idle': discord.Status.idle,
            'dnd': discord.Status.dnd,
            'offline': discord.Status.offline
        }
        if new_status not in statuses.keys():
            return await ctx.send("Invalid option, valid statuses are: `online`, `idle`, `dnd`, or `offline`")

        self.curStatus = statuses[new_status]
        await self.bot.change_presence(status=self.curStatus, activity=self.curActivity)
        await ctx.send(f"Status changed to {new_status}")

    @commands.guild_only()
    @checks.is_staff_or_perms("Mod", manage_roles=True)
    @commands.command()
    async def speak(self, ctx: commands.Context, channel: discord.TextChannel, *, message: str):
        """Make the bot speak"""
        await ctx.message.delete()
        await channel.send(message)

    @commands.group(invoke_without_command=True, aliases=['reminder'])
    async def remind(self, ctx: commands.Context, time: str, *, text: str):
        """Reminds you about something in dms! (Please make sure you have your dms on if you are using this from a server), time is in dhms format ie `10 minutes` would be `10m`"""
        time_seconds = common.parse_time(time)
        if time_seconds == -1:
            return await ctx.send("Invalid time passed!")

        if len(await self.bot.db.fetch(
                "SELECT * FROM timed_jobs WHERE type = 'reminder' AND extra->>'user_id'::text = $1",
                str(ctx.author.id))) + 1 > 10:
            return await ctx.send("You have too many reminders! you can delete some with remind del <number>")

        reminder_data = {
            "user_id": ctx.author.id,
            "reminder": text
        }
        await ctx.send(f"OK, I will remind you about `{text}`. Please make sure I can dm you!")
        await self.bot.scheduler.add_timed_job('reminder', creation=datetime.utcnow(),
                                               expiration=timedelta(seconds=time_seconds), **reminder_data)

    @remind.command(name="list")
    async def list_reminders(self, ctx: commands.Context):
        """Lists your current reminders"""

        reminders = []
        records = await self.bot.db.fetch("SELECT * FROM timed_jobs WHERE type = 'reminder' AND extra->>'user_id' = $1",
                                          str(ctx.author.id))
        for r in records:
            reminders.append(Reminder(r['id'], r['extra']['reminder'], r['expiration']))

        out = discord.Embed(title=f"Reminders for {ctx.author}", color=ctx.author.color.value)
        if len(reminders) == 0:
            out.description = "No reminders found. Use `remind` to set some"

        else:
            for num, r in enumerate(reminders, start=1):
                out.add_field(name=f"#{num}",
                              value=f"Job ID: {r.id} Reminder: `{r.reminder}`\nExpiration: `{r.time_stamp}`",
                              inline=False)

        out.set_footer(text=f"{len(reminders)} total reminder(s).")
        try:
            await ctx.author.send(embed=out)
            await ctx.message.add_reaction("\U0001f4ec")
        except discord.Forbidden:
            await ctx.send("I cannot dm you! please enable dms on this server!")

    @remind.command(name="deletereminder", aliases=['delreminder', 'delremind', 'deleteremind', 'del'])
    async def delete_reminder(self, ctx: commands.Context, reminder_num: int):
        """Deletes a reminder"""
        records = await self.bot.db.fetch("SELECT * FROM timed_jobs WHERE type = 'reminder' AND extra->>'user_id' = $1",
                                          str(ctx.author.id))
        deleted_reminder = None
        for num, r in enumerate(records, start=1):
            if num == reminder_num:
                deleted_reminder = Reminder(r['id'], r['extra']['reminder'], r['expiration'])

        if deleted_reminder:
            await self.bot.db.execute("DELETE FROM timed_jobs WHERE type = 'reminder' AND id = $1", deleted_reminder.id)
            await ctx.send("Reminder deleted.")
        else:
            await ctx.send("No reminder by that number found.")

    @commands.command(name="getcolor", aliases=['colorinfo'])
    async def get_color(self, ctx: commands.Context, *, color_in: str):
        """
        Gets a color given from a hexadecimal code or RGB triple.
        Hex - 6 characters long excluding the # (which is optional). Each character may go from 0 to F in hexadecimal.
        RGB - 3 numbers separated by a comma
        """
        mode = 'hex'
        hex_color_tuple = common.hex_to_color(color_in)
        if not hex_color_tuple:
            mode = 'rgb'

        rgb_color = common.parse_rgb(color_in)
        if not hex_color_tuple and not rgb_color:
            return await ctx.send("Unable to parse your input. Command accepts hex or RGB.")

        if mode == 'rgb':
            if not rgb_color:
                return await ctx.send("Unable to parse RGB.")
            e = discord.Embed(title=f"Color RGB {', '.join(map(lambda c: str(c), rgb_color))}",
                              color=discord.Color.from_rgb(*rgb_color), description=f"Color Hex: {webcolors.rgb_to_hex(rgb_color)}")
            color_file = common.image_from_rgb(rgb_color)
            e.set_image(url="attachment://color.png")
            return await ctx.send(embed=e, file=color_file)

        elif mode == "hex":
            if not hex_color_tuple:
                return ctx.send("Unable to parse hex code.")
            e = discord.Embed(title=f"Color Hex {hex_color_tuple[1]}", color=hex_color_tuple[0], description=f"Color RGB {', '.join(map(lambda x: str(x), tuple(webcolors.hex_to_rgb(hex_color_tuple[1]))))}")
            color_file = common.image_from_rgb(webcolors.hex_to_rgb(hex_color_tuple[1]))
            e.set_image(url="attachment://color.png")
            return await ctx.send(embed=e, file=color_file)


def setup(bot):
    bot.add_cog(Misc(bot))
