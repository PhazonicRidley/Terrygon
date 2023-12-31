import discord
import asyncio
from datetime import datetime, timedelta
from utils import errors


class TimedJob:

    def __init__(self, record):
        self.id = record['id']
        self.type = record['type']
        self.expiration = record['expiration']
        self.extra = record['extra']


class Scheduler:
    """Handles scheduling timed jobs"""

    def __init__(self, bot):
        self.bot = bot
        self.actions = {
            'mute': self.time_unmute,
            'ban': self.time_unban,
            # 'block': self.time_unblock,
            'reminder': self.remind
        }

    async def add_timed_job(self, type: str, creation: datetime, expiration: timedelta, **kwargs):
        """Function to add a timed job to the database"""

        # adds time to the creation in seconds
        expiration += creation
        if (expiration - creation).total_seconds() <= 60:
            await asyncio.sleep((expiration - creation).total_seconds())
            await self.actions[type](**kwargs)

            return

        if not kwargs:
            query = "INSERT INTO timed_jobs (type, expiration) VALUES ($1, $2)"
            args = [type, expiration]
        else:
            query = "INSERT INTO timed_jobs (type, expiration, extra) VALUES ($1, $2, $3)"
            args = [type, expiration, kwargs]

        await self.bot.db.execute(query, *args)

    async def run_timed_jobs(self):
        """Runs timed jobs"""
        # try:
        while not self.bot.is_closed():
            job = await self.get_job()
            if job:
                current_time = datetime.utcnow()
                if job.expiration >= current_time:
                    await asyncio.sleep((job.expiration - current_time).total_seconds())
                    await self.actions[job.type](**job.extra)
                    await self.bot.db.execute("DELETE FROM timed_jobs WHERE id = $1",
                                              job.id)  # remove the job from the db

                else:
                    await self.actions[job.type](**job.extra)
                    await self.bot.db.execute("DELETE FROM timed_jobs WHERE id = $1",
                                              job.id)  # remove the job from the db

    async def get_job(self):
        """Get the latest timed job"""
        record = await self.bot.db.fetchrow(
            """SELECT * FROM timed_jobs WHERE "expiration" < (CURRENT_DATE + $1::interval) ORDER BY "expiration" LIMIT 1""",
            timedelta(days=10))
        return TimedJob(record) if record else None

    # function to add jobs
    # function to run jobs and remove them from the db
    # then add timed mod commands

    async def get_data(self, action_id: int, table: str) -> (tuple, None):
        """Gets data from database about various mod actions and returns discord objects or IDs"""
        table = table.lower()
        if table not in ('mutes', 'bans'):
            raise TypeError("Table type does not exist.")

        action_record = await self.bot.db.fetchrow(f"SELECT * FROM {table} WHERE id = $1", action_id)
        if action_record is None:
            return None

        guild = self.bot.get_guild(action_record['guild_id'])
        author = guild.get_member(action_record['author_id'])
        user = guild.get_member(action_record['user_id'])
        if guild is None:
            # properly log later THIS SHOULD TRIGGER ALMOST NEVER
            await self.bot.db.execute(f"DELETE FROM {table} WHERE id = $1", action_id)
            return None

        if user is None:
            try:
                user = await self.bot.fetch_user(action_record['user_id'])
            except discord.NotFound:
                user = action_record['user_id']

        if author is None:
            try:
                author = await self.bot.fetch_user(action_record['author_id'])
            except discord.NotFound:
                author = action_record['author_id']

        return guild, author, user

    async def time_unmute(self, **kwargs):
        """Unmutes a user from a timemute"""
        mute_id = kwargs['action_id']
        data = await self.get_data(mute_id, "mutes")
        if data:
            guild, author, user = data
        else:
            return

        muted_role = guild.get_role(
            await self.bot.db.fetchval("SELECT muted_role FROM roles WHERE guild_id = $1", guild.id))
        if muted_role is None:
            return await self.bot.terrygon_logger.custom_log("mod_logs", guild, f":warning: **Muted role could not be found !** Could not unmute user.")

        await self.bot.db.execute("DELETE FROM mutes WHERE id = $1", mute_id)
        if isinstance(user, discord.Member):
            try:
                await user.remove_roles(muted_role, reason="Time mute expired")
            except discord.Forbidden:
                try:
                    await guild.owner.send(f"Cannot unmute on {guild.name} a timed mute because I cannot manage roles")
                except discord.Forbidden:
                    pass

        if isinstance(user, discord.Member):
            try:
                await user.send(f"You have been unmuted in {guild.name}")
            except discord.Forbidden:
                pass

        try:
            await self.bot.terrygon_logger.expiration_mod_logs('mute', guild, author, user)
        except errors.LoggingError:
            pass

    async def time_unban(self, **kwargs):
        """Unmutes a user from a timemute"""
        ban_id = kwargs['action_id']
        data = await self.get_data(ban_id, "bans")
        if data:
            guild, author, user = data
        else:
            return

        await self.bot.db.execute("DELETE FROM bans WHERE user_id = $1 AND guild_id = $2", user.id, guild.id)
        if isinstance(user, discord.User):
            try:
                await guild.unban(user, reason="Timeban expired")
            except discord.Forbidden:
                pass

        try:
            await self.bot.terrygon_logger.expiration_mod_logs('ban', guild, author, user)
        except errors.LoggingError:
            pass

    async def remind(self, **reminder):
        """Reminds a user"""
        user = self.bot.get_user(reminder['user_id'])
        if not user:
            return
        try:
            await user.send(f"You wanted to be reminded about: `{reminder['reminder']}`")
        except discord.Forbidden:
            return
