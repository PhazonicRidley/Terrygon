import discord
from discord.ext import commands, menus
from discord.utils import escape_mentions
import re

from utils import paginator


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
    async def add(self, ctx, acc_type, acc_data):
        """Add an account (acc_type is the kind of account you wish to add, while acc_data is your account name or friend code)"""
        if acc_type.lower() in ('switch', '3ds'):
            if not re.fullmatch(r'\d\d\d\d\-?\d\d\d\d\-?\d\d\d\d', acc_data):
                return await ctx.send(f"Invalid {acc_type} friendcode")
            else:
                if acc_data[4].isdigit() and acc_data[8].isdigit():
                    acc_data = acc_data[:3] + '-' + acc_data[3:]
                    acc_data = acc_data[:8] + '-' + acc_data[8:]

        async with self.bot.db.acquire() as conn:
            if await conn.fetchval("SELECT accounts FROM accountinfo WHERE userid = $1", ctx.author.id) is None:
                final_query = "UPDATE accountinfo SET accounts = jsonb_build_object($1::TEXT, $2::TEXT) WHERE userid = $3"
            else:
                final_query = "UPDATE accountinfo SET accounts = accounts::jsonb || jsonb_build_object($1::TEXT, $2::TEXT) WHERE userid = $3"

            # TODO check for valid friend codes
            await conn.execute(final_query, escape_mentions(acc_type), escape_mentions(acc_data), ctx.author.id)
            await ctx.send(f"Added your {escape_mentions(acc_type)} account: `{escape_mentions(acc_data)}`")

    @account.command(aliases=['del'])
    async def delete(self, ctx, acc_type):
        """Deletes an account. If you would like to delete all your accounts, do accounts delete all"""
        if acc_type.lower() == 'all':
            if await self.bot.db.execute("SELECT accounts FROM accountinfo WHERE userid = $1", ctx.author.id) is None:
                return await ctx.send("No accounts saved")

            res, msg = await paginator.YesNoMenu(
                "Are you sure you want to clear all your accounts? This cannot be reversed!").prompt(ctx)
            if res:
                await self.bot.db.execute("UPDATE accountinfo SET accounts = NULL WHERE userid = $1", ctx.author.id)
                return await msg.edit(content="All accounts cleared!")
            else:
                return await msg.edit(content="Cancelled")
        else:
            acc_type = escape_mentions(acc_type)
            async with self.bot.db.acquire() as conn:
                if await conn.fetchval("SELECT accounts->>$1 FROM accountinfo WHERE userid =$2", acc_type,
                                       ctx.author.id) is None:
                    return await ctx.send("This account does not exist")
                else:
                    await conn.execute("UPDATE accountinfo SET accounts = accounts::jsonb - $1 WHERE userid = $2",
                                       acc_type, ctx.author.id)
                    if not await conn.fetchval("SELECT accounts FROM accountinfo WHERE userid = $1", ctx.author.id):
                        await conn.execute("UPDATE accountinfo SET accounts = NULL WHERE userid = $1", ctx.author.id)

                    return await ctx.send(f"Deleted {acc_type} account!")

    @account.command()
    async def list(self, ctx, member: discord.Member = None):
        """List a user's accounts or your own"""
        if member is None:
            member = ctx.author

        accounts = await self.get_accounts(member.id)
        embed = discord.Embed(colour=member.colour.value)
        embed.set_author(name=f"Accounts saved for {member.name}#{member.discriminator}:", icon_url=member.avatar_url)
        if accounts is None:
            embed.description = "No accounts saved"
        else:
            for acc_type, acc_data in accounts.items():
                embed.add_field(name=f"**{acc_type}**", value=acc_data, inline=False)

            embed.set_footer(
                text=f"{len(accounts)} total account" if len(accounts) == 1 else f"{len(accounts)} total accounts")

        await ctx.send(embed=embed)

    # util functions
    async def cog_before_invoke(self, ctx):
        """Runs before any command is ran"""
        await self.add_user_database(ctx.author.id)

    async def get_accounts(self, userid) -> dict:
        """Gets a user's accounts"""
        async with self.bot.db.acquire() as conn:
            json_data = await conn.fetchval("SELECT accounts FROM accountinfo WHERE userid = $1", userid)
            return json_data

    async def add_user_database(self, userid):
        """Adds a json config for a guild to store toggleable roles in"""
        async with self.bot.db.acquire() as conn:
            if await conn.fetchval("SELECT userid FROM accountinfo WHERE userid = $1", userid) is None:
                await conn.execute("INSERT INTO accountinfo (userid) VALUES ($1)", userid)


def setup(bot):
    bot.add_cog(AccountInfo(bot))
