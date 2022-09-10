import asyncpg
import discord
from discord.errors import Forbidden
from discord.ext import commands, flags
from utils import checks, errors, custom_views


class Approval(commands.Cog):
    """Approval System"""
    def __init__(self, bot):
        self.bot = bot

    @commands.guild_only()
    @checks.is_staff_or_perms("Owner", administrator=True)
    @commands.group(name="approvalsystem", invoke_without_command=True)
    async def approval_system_manager(self, ctx: commands.Context):
        """Manages a server's approval system."""
        await ctx.send_help(ctx.command)

    @commands.guild_only()
    @checks.is_staff_or_perms("Owner", administrator=True)
    @approval_system_manager.command(name="toggle")
    async def toggle(self, ctx: commands.Context):
        """Enables or disables a server's approval system"""
        async with self.bot.db.acquire() as conn:
            approval_role_id = await conn.fetchval("SELECT approved_role FROM roles WHERE guild_id = $1", ctx.guild.id)
            approval_channel_id = await conn.fetchval("SELECT approval_channel FROM channels WHERE guild_id = $1", ctx.guild.id)
            if approval_role_id is None or approval_channel_id:
                await ctx.reply("Missing registered approval role or approval gateway channel. To configure these, please use `approvalsystem configure`. This command is for enabling or disabling an existing approval system!")
                return

            status = await conn.fetchval("SELECT approval_system FROM guild_settings WHERE guild_id = $1", ctx.guild.id)
            if status:
                await conn.execute("UPDATE guild_settings SET approval_system = FALSE WHERE guild_id = $1", ctx.guild.id)
                try:
                    await self.bot.terrygon_logger.toggle_log_setup('unset', 'approval system', ctx.author, 'mod_logs')
                except errors.LoggingError:
                    pass
                await ctx.reply("Approval system disabled")

            else:
                await conn.execute("UPDATE guild_settings SET approval_system = TRUE WHERE guild_id = $1", ctx.guild.id)
                try:
                    await self.bot.terrygon_logger.toggle_log_setup('set', 'approval system', ctx.author, 'mod_logs')
                except errors.LoggingError:
                    pass
                await ctx.reply("Approval system enabled! use approve to let new members in")

    # TODO: redo this entire command
    # @commands.guild_only()
    # @checks.is_staff_or_perms("Owner", administrator=True)
    # @flags.add_flag('--channel', '-c', type=discord.TextChannel, default=None)
    # @flags.add_flag('--role', '-r', type=discord.Role, default=None)
    # @approval_system_manager.command(cls=flags.FlagCommand)
    # async def configure(self, ctx: commands.Context, **flag_options):
    #     """Configure a server to use an approval system"""
    #     approval_role = None
    #     approval_channel = None
    #     if not flag_options['channel']:
    #         confirmation = custom_views.Confirmation("Approval gateway channel created!", "No channel given")
    #         await ctx.reply("No approval gateway channel specified, would you like me to make a new channel for this?",
    #                         view=confirmation)
    #         await confirmation.wait()
    #         if confirmation.value:
    #             try:
    #                 approval_channel = await ctx.guild.create_text_channel('approval', reason="Approval gateway channel")
    #                 await approval_channel.edit(position=1)
    #             except discord.Forbidden:
    #                 await msg.edit(content="Unable to manage channels!")
    #                 return
    #         else:
    #             await msg.edit(
    #                 content="You need an approval gateway channel for the approval system to work properly, if you have an existing one specify one with `-c <channel>`")
    #     else:
    #         approval_channel = flag_options['channel']
    #
    #     if not flag_options['role']:
    #         res, msg = await paginator.YesNoMenu("No approval role specified, would you like to make one?").prompt(ctx)
    #         if res:
    #             try:
    #                 everyone_perms = ctx.guild.default_role.permissions
    #                 approval_role = await ctx.guild.create_role(name='Approved', permissions=everyone_perms)
    #             except discord.Forbidden:
    #                 await msg.edit(content='I cannot manage roles!')
    #                 return
    #             await msg.edit(content="Approval role created!")
    #         else:
    #             await msg.edit(
    #                 content="You need an approval role for the approval system to work properly, if you have an existing one specify one with `-r <role>`")
    #
    #     else:
    #         approval_role = flag_options['role']
    #
    #     # enter data into the database
    #     if approval_role is None or approval_channel is None:
    #         return await ctx.reply("Invalid data given, please run this command again")
    #
    #     async with self.bot.db.acquire() as conn:
    #         await conn.execute(
    #             "UPDATE guild_settings SET approval_system = TRUE WHERE guild_id = $1", ctx.guild.id)
    #         await conn.execute("UPDATE channels SET approval_channel = $1 WHERE guild_id = $2", approval_channel.id, ctx.guild.id)
    #         await conn.execute("UPDATE roles SET approved_role = $1 WHERE guild_id =$2", approval_role.id, ctx.guild.id)
    #
    #     # now to set the permissions up
    #     try:
    #         await approval_channel.set_permissions(approval_role, read_messages=False)
    #         for channel in ctx.guild.channels:
    #             if channel.overwrites_for(
    #                     ctx.guild.default_role).read_messages is not False and not channel.permissions_synced and channel != approval_channel:
    #                 await channel.set_permissions(approval_role, read_messages=True)
    #                 await channel.set_permissions(ctx.guild.default_role, read_messages=False)
    #
    #             if channel.overwrites_for(ctx.guild.default_role).send_messages is False:
    #                 await channel.set_permissions(approval_role, send_messages=False)
    #
    #     except discord.Forbidden:
    #         return await ctx.reply("Unable to manage roles and channels!")
    #
    #     await ctx.reply("All permissions have been configured")
    #     try:
    #         await self.bot.terrygon_logger.approval_config(ctx.author, approval_channel, approval_role)
    #     except errors.LoggingError:
    #         pass

    @commands.guild_only()
    @checks.is_staff_or_perms("Owner", administrator=True)
    @approval_system_manager.command()
    async def remove(self, ctx: commands.Context):
        """Disables and removes an approval system fully from a server"""
        async with self.bot.db.acquire() as conn:
            if not await conn.fetchval("SELECT approval_system FROM guild_settings WHERE guild_id = $1", ctx.guild.id):
                return await ctx.reply("You do not have an approval system enabled, and thus do not need this!")

            approval_role = ctx.guild.get_role(
                await conn.fetchval("SELECT approved_role FROM roles WHERE guild_id = $1", ctx.guild.id))
            approval_channel = ctx.guild.get_channel(
                await conn.fetchval("SELECT approval_channel FROM channels WHERE guild_id = $1", ctx.guild.id))

        # remove all permissions that the approval system needed
        if approval_role:
            for channel in ctx.guild.channels:
                if not channel.permissions_synced and channel.overwrites_for(approval_role).read_messages:
                    await channel.set_permissions(ctx.guild.default_role, read_messages=None)

            confirmation = custom_views.Confirmation("Approval role deleted!", "Role not deleted.")
            msg = await ctx.reply("Would you like to delete the approval role?", view=confirmation)
            await confirmation.wait()
            if confirmation.value:
                try:
                    await approval_role.delete(reason="Removing approval system")
                except discord.Forbidden:
                    await msg.edit(content="Cannot delete roles!")
        else:
            await self.bot.db.execute("UPDATE roles SET approved_role = NULL WHERE guild_id = $1", ctx.guild.id)
            await ctx.reply("Approval role has already been deleted, removing from database")

        if approval_channel:
            confirmation = custom_views.Confirmation("Channel deleted!", "Channel not deleted")
            msg = await ctx.reply("Would you like to delete the approval gateway channel?", view=confirmation)
            await confirmation.wait()
            if confirmation.value:
                try:
                    await approval_channel.delete(reason="Removing approval system")
                except discord.Forbidden:
                    await msg.edit(content="Cannot delete channels!")
        else:
            try:
                await self.bot.db.execute("UPDATE channels SET approval_channel = NULL WHERE guild_id = $1", ctx.guild.id)
            except asyncpg.UndefinedColumnError:
                pass
            await ctx.reply("Approval channel has already been delete, removing from database.")

        await self.bot.db.execute("UPDATE guild_settings SET approval_system = NULL WHERE guild_id = $1", ctx.guild.id)
        await self.bot.db.execute("DELETE FROM approved_members WHERE guild_id = $1", ctx.guild.id)
        try:
            await self.bot.terrygon_logger.approval_deletion(ctx.author, approval_channel, approval_role)
        except errors.LoggingError:
            pass

    @commands.guild_only()
    @checks.is_staff_or_perms("Mod", manage_roles=True)
    @commands.command()
    async def approve(self, ctx: commands.Context, member: discord.Member):
        """Approve members"""

        async with self.bot.db.acquire() as conn:
            if not await conn.fetchval("SELECT approval_system FROM guild_settings WHERE guild_id = $1", ctx.guild.id):
                await ctx.reply("Approval system disabled, you have no need for this!")
                return

            approved_role = ctx.guild.get_role(await conn.fetchval("SELECT approved_role FROM roles WHERE guild_id = $1", ctx.guild.id))
            if approved_role in member.roles or await conn.fetchval(
                    "SELECT user_id FROM approved_members WHERE guild_id = $1", ctx.guild.id) == member.id:
                await ctx.reply("Member already approved")
                return

            try:
                await member.add_roles(approved_role)
                await ctx.reply(f"{self.bot.terrygon_logger.emotes['approve']} {member} has been approved!")
                await self.bot.terrygon_logger.mod_logs(ctx, 'approve', member, ctx.author)
            except Forbidden:
                return await ctx.reply("Cannot add roles, please check my permissions")

            await conn.execute("INSERT INTO approved_members (user_id, guild_id) VALUES ($1, $2)", member.id,
                               ctx.guild.id)

            try:
                await member.reply(
                    f"You have been approved on {ctx.guild.name} welcome, please read the rules of the server!")
            except Forbidden:
                pass

    @commands.guild_only()
    @checks.is_staff_or_perms("Mod", manage_roles=True)
    @commands.command()
    async def unapprove(self, ctx: commands.Context, member: discord.Member):
        """Unapprove members"""

        async with self.bot.db.acquire() as conn:
            if not await conn.fetchval("SELECT approval_system FROM guild_settings WHERE guild_id = $1", ctx.guild.id):
                await ctx.reply("Approval system disabled, you have no need for this!")
                return

            approved_role = ctx.guild.get_role(
                await conn.fetchval("SELECT approved_role FROM roles WHERE guild_id = $1", ctx.guild.id))
            if not approved_role in member.roles or not await conn.fetchval(
                    "SELECT user_id FROM approved_members WHERE guild_id = $1", ctx.guild.id):
                await ctx.reply("Member not approved")
                return

            try:
                await member.remove_roles(approved_role)
                await ctx.reply(f"{self.bot.terrygon_logger.emotes['unapprove']} {member} has been unapproved")
                await self.bot.terrygon_logger.mod_logs(ctx, 'unapprove', member, ctx.author)
            except Forbidden:
                await ctx.reply("Unable to remove roles, please check my permissions")
                return

            await conn.execute("DELETE FROM approved_members WHERE user_id = $1 AND guild_id = $2", member.id,
                               ctx.guild.id)


async def setup(bot):
    await bot.add_cog(Approval(bot))
