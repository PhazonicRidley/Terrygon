import typing

import discord
from discord.ext import commands
from utils import checks, self_roles, paginator


class ToggleRoles(commands.Cog):
    """Cog to handle self roles."""

    def __init__(self, bot):
        self.bot = bot

    @commands.guild_only()
    @commands.group(name="togglerole", invoke_without_command=True)
    async def toggle_role(self, ctx: commands.Context, *, keywords: str = None):
        """Toggles a self role"""
        if not keywords:
            return await self_roles.list_all_roles(ctx, 'toggle_roles')

        keywords = keywords.replace(" ", "").split(",")
        data = await self.bot.db.fetch("SELECT keyword FROM toggle_roles WHERE guild_id = $1", ctx.guild.id)
        saved_keywords = list(map(lambda x: x['keyword'], data))
        valid_keywords = []
        invalid_keywords = []
        for kw in keywords:
            if kw in saved_keywords:
                valid_keywords.append(kw)
            else:
                invalid_keywords.append(kw)

        error_keywords = []
        joined_keywords = []
        left_keywords = []
        bot_perms = ctx.guild.get_member(self.bot.user.id).guild_permissions
        if not bot_perms.manage_roles:
            return await ctx.send("Unable to add roles due to lack of permissions")

        for kw in valid_keywords:
            res = await self.role_toggle(ctx, kw)
            if res == -1:
                error_keywords.append(kw)
            elif res == 1:
                left_keywords.append(kw)
            elif res == 0:
                joined_keywords.append(kw)

        embed = discord.Embed(title="Toggled roles", color=ctx.author.color)
        if joined_keywords:
            embed.add_field(name="Joined:", value=", ".join(joined_keywords), inline=False)
        if left_keywords:
            embed.add_field(name="Left:", value=", ".join(left_keywords), inline=False)
        if invalid_keywords:
            embed.add_field(name="No toggleable roles for the keywords:", value=", ".join(invalid_keywords),
                            inline=False)
        if error_keywords:
            embed.add_field(name="Role no longer exists for:", value=", ".join(error_keywords), inline=False)

        await ctx.send(embed=embed)

    async def role_toggle(self, ctx: commands.Context, keyword: str) -> int:
        """Applies a self role."""
        keyword = keyword.lower()
        role_id = await self.bot.db.fetchval("SELECT role_id FROM toggle_roles WHERE guild_id = $1 AND keyword = $2",
                                             ctx.guild.id, keyword)
        role = ctx.guild.get_role(role_id)
        if not role:
            return -1

        has_role = role in ctx.author.roles
        if has_role:
            try:
                await ctx.author.remove_roles(role, reason="Removed toggle role.")
            except discord.Forbidden:
                return -1

            return 1
        else:
            try:
                await ctx.author.add_roles(role, reason="Added toggle role.")
            except discord.Forbidden:
                return -1

            return 0

    @commands.guild_only()
    @checks.is_staff_or_perms("Mod", manage_roles=True)
    @toggle_role.command(name="add")
    async def add_toggle_role(self, ctx: commands.Context, emoji: str, keyword: str,
                              role: typing.Union[discord.Role, str], *, description: str = None):
        """Adds a toggleable role"""
        keyword = keyword.lower()
        if keyword in ("add", "remove", "del", "delete", "list", "info"):
            return await ctx.send("Cannot make a keyword this.")
        if await self_roles.check_existing_keyword_roles(ctx, 'toggle_roles', keyword) == -1:
            return

        await self_roles.add_self_role(ctx, 'toggle_roles', role, emoji=emoji, keyword=keyword, description=description)
        await ctx.send(f"Added toggleable role {role} with keyword {keyword}")

    @commands.guild_only()
    @checks.is_staff_or_perms("Mod", manage_roles=True)
    @toggle_role.command(name="remove", aliases=['del', 'delete'])
    async def remove_toggle_role(self, ctx: commands.Context, keyword: str):
        """Removes a toggleable role."""
        keyword = keyword.lower()
        if await self_roles.delete_self_role(ctx, "toggle_roles", ('keyword', keyword)) == 0:
            await ctx.send(f"Toggleable role bound to {keyword} deleted.")

    @commands.guild_only()
    @checks.is_staff_or_perms("Owner", adminstrator=True)
    @toggle_role.command(name="removeall", aliases=['delall', 'deleteall'])
    async def remove_all_toggles(self, ctx: commands.Context):
        """Removes all toggle roles"""
        await self_roles.delete_all_roles(ctx, 'toggle_roles')

    @commands.guild_only()
    @toggle_role.command(name="list")
    async def toggle_role_list(self, ctx: commands.Context, keyword: str = None):
        """Lists toggle roles"""
        if not keyword:
            await self_roles.list_all_roles(ctx, 'toggle_roles')
        else:
            await self_roles.get_role_info(ctx, 'toggle_roles', ('keyword', keyword))

    @commands.guild_only()
    @toggle_role.command(name="info")
    async def toggle_role_info(self, ctx: commands.Context, keyword: str):
        """Gets info on a toggle role."""
        await self_roles.get_role_info(ctx, "toggle_roles", ("keyword", keyword))


def setup(bot):
    bot.add_cog(ToggleRoles(bot))
