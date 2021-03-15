import os

import discord
from discord.ext import commands
import asyncio
import time
from datetime import datetime, timedelta
from utils import errors
from logzero import setup_logger

console_logger = setup_logger(name="schedule_logs", logfile="logs/scheduler.log", maxBytes=100000)


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

        if not os.path.exists("logs.log"):
            open("logs/scheduler.log", "w").write("")

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

    async def time_unmute(self, **kwargs):
        """Unmutes a user from a timemute"""
        mute_id = kwargs['action_id']
        mute_record = await self.bot.db.fetchrow("SELECT * FROM mutes WHERE id = $1", mute_id)
        if mute_record is None:
            return

        guild = self.bot.get_guild(mute_record['guildid'])
        author = guild.get_member(mute_record['authorid'])
        user = guild.get_member(mute_record['userid'])

        if None in (guild, author, user):
            err = f"Cannot process a timed unmute with id {mute_id} cannot find either the guild, author, or user. guild: {guild}, author: {author}, user {user}"
            print(err)
            console_logger.info(err)
            return

        muted_role = guild.get_role(
            await self.bot.db.fetchval("SELECT mutedrole FROM roles WHERE guildid = $1", guild.id))
        if muted_role is None:
            try:
                await guild.owner.send("Unable to unmute a timed mute, muted role is not set.")
            except discord.Forbidden:
                pass
            return
        try:
            await user.remove_roles(muted_role, reason="Time mute expired")
            await self.bot.db.execute("DELETE FROM mutes WHERE userID = $1 AND guildID = $2", user.id, guild.id)
        except discord.Forbidden:
            try:
                await guild.owner.send(f"Cannot unmute on {guild.name} a timed mute because I cannot manage roles")
            except discord.Forbidden:
                pass

        try:
            await user.send(f"You have been unmuted in {guild.name}")
        except discord.Forbidden:
            pass

        try:
            await self.bot.discord_logger.expiration_mod_logs('mute', guild, author, user)
        except errors.loggingError:
            pass

    async def time_unban(self, **kwargs):
        """Unmutes a user from a timemute"""
        ban_id = kwargs['action_id']
        ban_record = await self.bot.db.fetchrow("SELECT * FROM bans WHERE id = $1", ban_id)
        if ban_record is None:
            return
        guild = self.bot.get_guild(ban_record['guildid'])
        author = guild.get_member(ban_record['authorid'])
        user = await self.bot.fetch_user(ban_record['userid'])

        if None in (guild, author, user):
            s = f"Time unban with ban_id {ban_id} could not be processed because either the guild, author, or banned user was not found in the database! guild: {guild}, author: {author}, user: {user}"
            print(s)
            console_logger.info(s)
            return

        try:
            await guild.unban(user, reason="Timeban expired")
            await self.bot.db.execute("DELETE FROM bans WHERE userid = $1 AND guildid = $2", user.id, guild.id)
        except discord.Forbidden:
            pass

        try:
            await self.bot.discord_logger.expiration_mod_logs('ban', guild, author, user)
        except errors.loggingError:
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
