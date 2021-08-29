import discord
from discord.ext import commands, flags
from utils import checks, common
import typing


class Trusted(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    async def get_trusted_list(self, guild_id: int) -> list:
        """Returns a list of trusted user ids for a guild, or None if none are found"""
        return await self.bot.db.fetchval("SELECT trusted_uid FROM trusted_users WHERE guild_id = $1", guild_id)

    @commands.guild_only()
    @flags.add_flag('--id', '-i', action="store_true", default=False)
    @flags.command(name="listtrusted", aliases=['trustlist', 'trusted_users', 'trustedlist'])
    async def list_trusted(self, ctx: commands.Context, **flag_arg):
        """Lists a guild's trusted users"""
        trusted_ids = await self.get_trusted_list(ctx.guild.id)
        embed = discord.Embed(title=f"Trusted users for {ctx.guild.name}", colour=common.gen_color(ctx.guild.id))

        if not trusted_ids:
            embed.description = "No trusted users!"
            return await ctx.send(embed=embed)

        deleted_users = ""
        trusted_user_str = ""
        for uid in trusted_ids:
            user = self.bot.get_user(uid) if self.bot.get_user(uid) else await self.bot.fetch_user(uid)
            if user is None:
                deleted_users = True
                deleted_users += f"- \U000026a0 {uid}\n"
            else:
                trusted_user_str += f"- {user}"
                if flag_arg['id']:
                    trusted_user_str += f" ({uid})"
                trusted_user_str += "\n"

        embed.description = trusted_user_str
        if deleted_users:
            embed.add_field(name="**Deleted user IDs!**",
                            value=deleted_users + "\nPlease delete these users from the database!")
        await ctx.send(embed=embed)

    @commands.guild_only()
    @checks.is_staff_or_perms("Admin", manage_guild=True)
    @commands.command()
    async def trust(self, ctx: commands.Context, member: typing.Union[discord.Member, int]):
        """Adds a member to the guild's trusted list (Admin+ or manage server)"""
        if isinstance(member, int):
            try:
                member = await self.bot.fetch_user(member)
            except discord.NotFound:
                return await ctx.send("Invalid user given")
        trusted_list = await self.get_trusted_list(ctx.guild.id)
        if trusted_list is None or member.id not in trusted_list:
            await self.bot.db.execute(
                "UPDATE trusted_users SET trusted_uid = array_append(trusted_uid, $1) WHERE guild_id = $2", member.id,
                ctx.guild.id)
            await ctx.send(f"Added {member} to {ctx.guild.name}'s trusted list!")
        else:
            await ctx.send("This user is already trusted!")

    @commands.guild_only()
    @checks.is_staff_or_perms("Admin", manage_guild=True)
    @commands.command()
    async def untrust(self, ctx: commands.Context, member: typing.Union[discord.Member, int]):
        """Removes a member to the guild's trusted list (Admin+ or manage server)"""
        trusted_list = await self.get_trusted_list(ctx.guild.id)
        if isinstance(member, discord.Member):
            member = member.id

        if trusted_list is None or len(trusted_list) == 0:
            return await ctx.send("No trusted users saved")

        elif member in trusted_list:
            await self.bot.db.execute(
                "UPDATE trusted_users SET trusted_uid = array_remove(trusted_uid, $1) WHERE guild_id = $2", member,
                ctx.guild.id)
            await ctx.send(f"{ctx.guild.get_member(member) if ctx.guild.get_member(member) is not None else 'User'} has been removed from trusted list!")
        else:
            await ctx.send("This user is not trusted")

    @commands.guild_only()
    @checks.is_trusted_or_perms(manage_messages=True)
    @commands.command()
    async def pin(self, ctx: commands.Context, message: discord.Message):
        """Pins a message (Trusted+)"""
        if message.guild != ctx.guild:
            return await ctx.send("You cannot pin messages in other servers!")

        if message.pinned:
            return await ctx.send("Message has already been pinned")

        try:
            await message.pin()
        except discord.Forbidden:
            return await ctx.send("I do not have permission to pin messages!")

        except discord.HTTPException:
            return await ctx.send("This channel has 50 pinned messages, please remove one before adding more")

        await self.bot.terrygon_logger.message_pinned('pin', ctx.author, message)

    @commands.guild_only()
    @checks.is_trusted_or_perms(manage_messages=True)
    @commands.command()
    async def unpin(self, ctx: commands.Context, message: discord.Message):
        """Unpins a message (Trusted+)"""
        if message.guild != ctx.guild:
            return await ctx.send("You cannot unpin messages in other servers!")

        if not message.pinned:
            return await ctx.send("Message is not pinned")

        try:
            await message.unpin()
        except discord.Forbidden:
            return await ctx.send("I do not have permission to unpin messages")

        await ctx.send("Message unpinned")
        await self.bot.terrygon_logger.message_pinned('unpin', ctx.author, message)


def setup(bot):
    bot.add_cog(Trusted(bot))
