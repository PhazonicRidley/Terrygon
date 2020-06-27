import discord
from discord.ext import commands, menus
from discord.utils import escape_mentions
import re

# TODO modularize
class AccountInfo(commands.Cog):
    """Module to store user's accounts"""

    def __init__(self, bot):
        self.bot = bot

    @commands.group(invoke_without_command=True, aliases=['accounts'])
    async def account(self, ctx):
        """Command for managing accounts"""
        await ctx.send("This can store your accounts in the bot to be queried later")
        await ctx.send_help(ctx.command)

    @account.command()
    async def add(self, ctx, acctype, accdata):
        """Add an account (acctype is the kind of account you wish to add, while accdata is your account name or friend code)"""
        if acctype.lower() in ('switch', '3ds'):
            if not re.fullmatch(r'\d\d\d\d\-?\d\d\d\d\-?\d\d\d\d', accdata):
                return await ctx.send(f"Invalid {acctype} friendcode")
            else:
                if accdata[4].isdigit() and accdata[8].isdigit():
                   accdata = accdata[:3] + '-' + accdata[3:]
                   accdata = accdata[:8] + '-' + accdata[8:]

        async with self.bot.db.acquire() as conn:
            if await conn.fetchval("SELECT accounts FROM accountinfo WHERE userid = $1", ctx.author.id) is None:
                finalquery = "UPDATE accountinfo SET accounts = jsonb_build_object($1::TEXT, $2::TEXT) WHERE userid = $3"
            else:
                finalquery = "UPDATE accountinfo SET accounts = accounts::jsonb || jsonb_build_object($1::TEXT, $2::TEXT) WHERE userid = $3"""

            # TODO check for valid friend codes
            await conn.execute(finalquery, escape_mentions(acctype), escape_mentions(accdata), ctx.author.id)
            await ctx.send(f"Added your {escape_mentions(acctype)} account: `{escape_mentions(accdata)}`")

    @account.command(aliases=['del'])
    async def delete(self, ctx, acctype):
        """Deletes an account. If you would like to delete all your accounts, do accounts delete all"""
        if acctype.lower() == 'all':
            if await self.bot.db.execute("SELECT accounts FROM accountinfo WHERE userid = $1", ctx.author.id) is None:
                return await ctx.send("No accounts saved")

            res, msg = await YesNoMenu(
                "Are you sure you want to clear all your accounts? This cannot be reversed!").prompt(ctx)
            if res:
                await self.bot.db.execute("UPDATE accountinfo SET accounts = NULL WHERE userid = $1", ctx.author.id)
                return await msg.edit(content="All accounts cleared!")
            else:
                return await msg.edit(content="Cancelled")
        else:
            acctype = escape_mentions(acctype)
            async with self.bot.db.acquire() as conn:
                if await conn.fetchval("SELECT accounts->>$1 FROM accountinfo WHERE userid =$2", acctype,
                                       ctx.author.id) is None:
                    return await ctx.send("This account does not exist")
                else:
                    await conn.execute("UPDATE accountinfo SET accounts = accounts::jsonb - $1 WHERE userid = $2",
                                       acctype, ctx.author.id)
                    if not await conn.fetchval("SELECT accounts FROM accountinfo WHERE userid = $1", ctx.author.id):
                        await conn.execute("UPDATE accountinfo SET accounts = NULL WHERE userid = $1", ctx.author.id)

                    return await ctx.send(f"Deleted {acctype} account!")

    @account.command()
    async def list(self, ctx, member: discord.Member = None):
        """List a user's accounts or your own"""
        if member is None:
            member = ctx.author

        accounts = await self.getAccounts(member.id)
        embed = discord.Embed(colour=member.colour.value)
        embed.set_author(name=f"Accounts saved for {member.name}#{member.discriminator}:", icon_url=member.avatar_url)
        if accounts is None:
            embed.description = "No accounts saved"
        else:
            for acctype, accdata in accounts.items():
                embed.add_field(name=f"**{acctype}**", value=accdata, inline=False)

            embed.set_footer(text=f"{len(accounts)} total account" if len(accounts) == 1 else f"{len(accounts)} total accounts")

        await ctx.send(embed=embed)

    # util functions
    async def cog_before_invoke(self, ctx):
        """Runs before any command is ran"""
        await self.setupdbuserid(ctx.author.id)

    async def getAccounts(self, userid) -> dict:
        """Gets a user's accounts"""
        async with self.bot.db.acquire() as conn:
            jsondata = await conn.fetchval("SELECT accounts FROM accountinfo WHERE userid = $1", userid)
            return jsondata

    async def setupdbuserid(self, userid):
        """Adds a json config for a guild to store toggleable roles in"""
        async with self.bot.db.acquire() as conn:
            if await conn.fetchval("SELECT userid FROM accountinfo WHERE userid = $1", userid) is None:
                await conn.execute("INSERT INTO accountinfo (userid) VALUES ($1)", userid)


class YesNoMenu(menus.Menu):

    def __init__(self, initMsg):
        super().__init__(timeout=30.0)
        self.msg = initMsg
        self.result = None

    async def send_initial_message(self, ctx, channel):
        return await channel.send(self.msg)

    @menus.button('\N{WHITE HEAVY CHECK MARK}')
    async def yes(self, payload):
        self.result = True
        await self.clear_buttons(react=True)
        self.stop()

    @menus.button('\N{CROSS MARK}')
    async def no(self, payload):
        self.result = False
        await self.clear_buttons(react=True)
        self.stop()

    async def prompt(self, ctx):
        await self.start(ctx, wait=True)
        return self.result, self.message


def setup(bot):
    bot.add_cog(AccountInfo(bot))
