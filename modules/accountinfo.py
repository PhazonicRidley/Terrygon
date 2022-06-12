import typing
import discord
from discord.ext import commands
from utils import paginator, common


class AccountInfo(commands.Cog):
    """Cog for account info"""

    def __init__(self, bot):
        self.bot = bot

    @commands.group(name="account", aliases=['accounts'], invoke_without_command=True)
    async def account_info(self, ctx: commands.Context):
        await ctx.send_help(ctx.command)

    @account_info.command(name="add")
    async def account_add(self, ctx: commands.Context, name: str, *, acc: str):
        """Adds an account to a set name."""
        exists = await self.bot.db.fetchval("SELECT name FROM accounts WHERE user_id = $1 AND name = $2",
                                            ctx.author.id, name.lower())
        if exists:
            res, msg = await paginator.YesNoMenu(
                "An account by this name already exists, would you like to replace it?").prompt(ctx)
            if res:
                await msg.edit(content=f"`{name.title()}` updated.")
                await self.bot.db.execute("UPDATE accounts SET content = $1 WHERE user_id = $2 AND name = $3", acc, ctx.author.id, name.lower())
            else:
                await msg.edit(content="Account not updated.")
        else:
            await self.bot.db.execute("INSERT INTO accounts (user_id, name, content) VALUES ($1, $2, $3)",
                                      ctx.author.id, name.lower(), acc)
            await ctx.send(f"`{name.title()}` Added.")

    @account_info.command(name="remove", aliases=['del', 'delete'])
    async def account_remove(self, ctx: commands.Context, name: str):
        """Removes an account."""
        exists = await self.bot.db.fetchval("SELECT name FROM accounts WHERE user_id = $1 AND name = $2", ctx.author.id, name.lower())

        if exists:
            await self.bot.db.execute("DELETE FROM accounts WHERE user_id = $1 AND name = $2", ctx.author.id, name.lower())
            await ctx.send("Account deleted.")
        else:
            await ctx.send("Account does not exist.")

    async def list_out(self, ctx: commands.Context, user: typing.Union[discord.Member, int] = None):
        """Gets account info for a user"""
        if not user:
            user = ctx.author

        if isinstance(user, int):
            # api call to fetch user
            try:
                user = await self.bot.fetch_user(user)
            except discord.NotFound:
                return await ctx.send("User does not exist.")

        account_data = await self.bot.db.fetch("SELECT name, content FROM accounts WHERE user_id = $1", user.id)
        embed = discord.Embed(color=common.gen_color(user.id))
        embed.set_author(name=f"Accounts for {user}", icon_url=user.display_avatar.url)
        if not account_data:
            embed.description = "No accounts saved."
        else:
            for account in account_data:
                embed.add_field(name=f"**{account['name'].title()}**", value=account['content'], inline=False)
            embed.set_footer(text=f"{len(account_data)} total account" if len(
                account_data) == 1 else f"{len(account_data)} total accounts")

        await ctx.send(embed=embed)

    @account_info.command(name="list")
    async def account_list(self, ctx: commands.Context, user: typing.Union[discord.Member, int] = None):
        """Lists accounts for a given user, if none is given, lists for yourself."""
        await self.list_out(ctx, user)


async def setup(bot):
    await bot.add_cog(AccountInfo(bot))
