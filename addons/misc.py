from time import strftime

import discord
import yaml
from discord.ext import commands
from discord.utils import escape_mentions
from utils import checks, common
from datetime import datetime
import typing
import collections
from logzero import setup_logger

misccmdlogger = setup_logger(logfile="logs/misc.log", maxBytes=1000000)


class Misc(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        self.curActivity = discord.Game(self.bot.readConfig("activity"))
        self.curStatus = discord.Status.online

    @commands.command(aliases=['mc'])
    async def membercount(self, ctx):
        """Prints member count"""
        bots = 0
        for member in ctx.guild.members:
            if member.bot:
                bots += 1

        await ctx.send(f"{ctx.guild.name} has {ctx.guild.member_count - bots} members and {bots} bots")

    @commands.guild_only()
    @commands.command(aliases=['currentperms'])
    async def currentpermissions(self, ctx):
        """Lists the bot's current permissions"""
        permnames = []
        embed = discord.Embed(title=f"My permissions on {ctx.guild.name}", colour=ctx.me.color.value)
        botperms = ctx.me.guild_permissions
        for name, value in botperms:
            name = name.replace('_', ' ').title()
            if value:
                permnames.append(name)

        embed.add_field(name=f"Permission value: {botperms.value}", value=", ".join(permnames), inline=False)
        embed.add_field(name="Highest role location", value=f"My highest role {ctx.me.top_role.name}, is in position {ctx.me.top_role.position} out of {len(ctx.guild.roles) - 1}", inline=False)
        await ctx.send(embed=embed)

    @commands.command()
    async def ping(self, ctx):
        """Pong!"""
        mtime = ctx.message.created_at
        currtime = datetime.now()
        latency = currtime - mtime
        ptime = str(latency.microseconds / 1000.0)
        return await ctx.send(":ping_pong:! Pong! Response time: {} ms".format(ptime))

    @commands.command(aliases=['ui', 'onion'])
    async def userinfo(self, ctx, member: typing.Union[discord.Member, int, str] = None):
        """Prints userinfo on a member"""
        inserver = None
        if member == None:
            user = ctx.author
            inserver = True
        elif isinstance(member, int):
            try:
                user = await self.bot.fetch_user(member)
                inserver = False
            except discord.NotFound:
                return await ctx.send("💢 I cannot find that user")
        elif isinstance(member, discord.Member):
            user = member
            inserver = True
        elif isinstance(member, str):
            return await ctx.send("💢 I cannot find that user")

        if inserver:
            embed = discord.Embed(title=f'**Userinfo for {user.name}#{str(user.discriminator)}**',
                                  color=user.color.value)
            embed.description = f"""**User's ID:** {str(user.id)} \n **Join date:** {str(user.joined_at)} \n**Created on** {str(user.created_at)}\n **Current Status:** {str(user.status).upper() if str(user.status).lower() == "dnd" else str(user.status).title()}\n **User Activity:**: {str(user.activity)} \n **Default Profile Picture:** {str(user.default_avatar).title()}\n **Current Display Name:** {user.display_name}\n**Nitro Boost Date:** {str(user.premium_since)}\n **Current Top Role:** {str(user.top_role)}\n **Bot** {user.bot}\n **Color:** {str(hex(user.color.value)[2:]).zfill(6)}"""
            embed.set_thumbnail(url=user.avatar_url)
            await ctx.send(embed=embed)

        elif not inserver:
            try:
                ban = await ctx.guild.fetch_ban(user)
            except discord.NotFound:
                ban = None

            embed = discord.Embed(title=f'**Userinfo for {user.name}#{str(user.discriminator)}**')
            embed.description = f"**User's ID:** {str(user.id)} \n **Default Profile Picture:** {str(user.default_avatar)} \n  **Created on:** {str(user.created_at)}\n **Bot:** {user.bot}\n {f'**Banned, reason:** {ban.reason}' if ban is not None else ''}"
            embed.set_footer(text=f'{user.name}#{user.discriminator} is not in your server.')
            embed.set_thumbnail(url=user.avatar_url)
            await ctx.send(embed=embed)

    @commands.command(aliases=['avi'])
    async def avatar(self, ctx, member: typing.Union[discord.Member, int, str] = None):
        """Gets a user's avatar"""
        # TODO move this code to its own function
        inserver = None
        if member is None:
            user = ctx.author
            inserver = True
        elif isinstance(member, int):
            try:
                user = await self.bot.fetch_user(member)
                inserver = False
            except discord.NotFound:
                return await ctx.send("💢 I cannot find that user")
        elif isinstance(member, discord.Member):
            user = member
            inserver = True
        elif isinstance(member, str):
            await ctx.send("💢 I cannot find that user")
            return

        embed = discord.Embed(title=f"Avatar for {user.name}#{user.discriminator}",
                              color=user.color.value if inserver else 0x99aab5)
        embed.set_image(url=user.avatar_url_as(static_format='png'))
        await ctx.send(embed=embed)

    @commands.command()
    async def about(self, ctx):
        """Info about the bot"""
        await ctx.send("https://gitlab.com/PhazonicRidley/terrygon")

    @commands.guild_only()
    @commands.command(aliases=['serverinfo'])
    async def guildinfo(self, ctx):
        """Posts guild info"""
        embed = discord.Embed(title=f"**Server info for: {ctx.guild.name}**", colour=common.gen_color(ctx.guild.id))
        if ctx.guild.icon:
            embed.set_thumbnail(url=ctx.guild.icon_url)

        approvalsystem = "enabled" if await self.bot.db.fetchval(
            "SELECT approvalsystem FROM guild_settings WHERE guildid = $1", ctx.guild.id) else "disabled"

        embed.add_field(
            name="**Stats**",
            value=f":slight_smile: **__Number of emotes:__** {len(ctx.guild.emojis)}\n:soccer: **__Region__:** {str(ctx.guild.region).title()}\n:white_check_mark: **__Verification Level:__** {str(ctx.guild.verification_level).title()}\n{self.bot.discordLogger.emotes['creationdate']} **__Creation:__** {strftime(str(ctx.guild.created_at))}\n:eyes: **__Approval System:__** {approvalsystem.title()}\n{self.bot.discordLogger.emotes['id']} **__Guild ID:__** {ctx.guild.id}\n",
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
            modrole = ctx.guild.get_role(
                await conn.fetchval("SELECT modrole FROM roles WHERE guildid = $1", ctx.guild.id))
            modrole = "No Mod role set" if modrole is None else modrole

            adminrole = ctx.guild.get_role(
                await conn.fetchval("SELECT adminrole FROM roles WHERE guildid = $1", ctx.guild.id))
            adminrole = "No Admin role set" if adminrole is None else adminrole

            ownerrole = ctx.guild.get_role(
                await conn.fetchval("SELECT ownerrole FROM roles WHERE guildid = $1", ctx.guild.id))
            ownerrole = "No Owner role set" if ownerrole is None else ownerrole
            if approvalsystem == 'enabled':
                approvalrole = ctx.guild.get_role(
                    await conn.fetchval("SELECT approvedrole FROM roles WHERE guildid = $1", ctx.guild.id))
            else:
                approvalrole = "Approval System Disabled"

        embed.add_field(name="**Role Info**",
                        value=f":shield: **__Number Of Roles:__** {len(ctx.guild.roles)}\n:helicopter: **__Mod Role:__** {modrole}\n:hammer: **__Admin Role:__** {adminrole}\n:crown: **__Owner Role:__** {ownerrole}\n:+1: **__Approval Role:__** {approvalrole}",
                        inline=False)

        await ctx.send(embed=embed)

    @checks.is_bot_owner()
    @commands.command()
    async def activity(self, ctx, *, msg: str = None):
        """Change the bot's playing/watching/listening to activity (Bot Owners only)"""
        to = False
        if msg is None:
            await self.bot.change_presence()
            await ctx.send("Removing status")
            return

        if msg.split()[0].lower() == "watching":
            msg = msg[9:]
            actType = discord.ActivityType.watching

        elif msg.split()[0].lower() == "listening":
            if msg.split()[1].lower() == 'to':
                to = True
            msg = msg[10:]
            actType = discord.ActivityType.listening
        else:
            with open('config.yml', 'r+') as f:
                config = yaml.safe_load(f)
                config['activity'] = msg
                yaml.dump(config, f)
            actType = discord.ActivityType.playing

        if to:
            msg = msg[3:]
            out = f"Setting current status to: `{str(actType)[13:].title()} to {msg}" + '`'

        else:
            out = f"Setting current status to: `{str(actType)[13:].title()} {msg}" + '`'

        self.curActivity = discord.Activity(name=msg, type=actType)
        await self.bot.change_presence(status=self.curStatus, activity=self.curActivity)
        await ctx.send(out)

    @checks.is_bot_owner()
    @commands.command()
    async def status(self, ctx, newstatus):
        """Changes the bot's discord status, valid options are online, idle, dnd, or offline (Bot Owners only)"""
        newstatus = newstatus.lower()
        statuses = {
            'online': discord.Status.online,
            'idle': discord.Status.idle,
            'dnd': discord.Status.dnd,
            'offline': discord.Status.offline
        }
        if newstatus not in statuses.keys():
            return await ctx.send("Invalid option, valid statuses are: `online`, `idle`, `dnd`, or `offline`")

        self.curStatus = statuses[newstatus]
        await self.bot.change_presence(status=self.curStatus, activity=self.curActivity)
        await ctx.send(f"Status changed to {newstatus}")

    @checks.is_staff_or_perms("Mod", manage_roles=True)
    @commands.command()
    async def speak(self, ctx, channel: discord.TextChannel, *, message):
        """Make the bot speak"""
        await ctx.message.delete()
        await channel.send(escape_mentions(message))


def setup(bot):
    bot.add_cog(Misc(bot))
    
