import asyncio
from abc import ABC

import discord
from discord.ext import menus, commands


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


# BasicEmbedCommand taken from https://gitlab.com/lightning-bot/Lightning/-/blob/v3/utils/menus.py#L21
# GPLv3 Licensed - Copyright (c) 2020 - LightSage
class BasicEmbedMenu(menus.ListPageSource):
    def __init__(self, data, *, per_page, embed=None):
        self.embed = embed
        super().__init__(data, per_page=per_page)

    async def format_page(self, menu, entries):
        if self.embed:
            embed = self.embed
        else:
            embed = discord.Embed(color=discord.Color.greyple())
        embed.description = "\n".join(entries)
        embed.set_footer(text=f"Page {menu.current_page + 1} of {self.get_max_pages()}")
        return embed


class ReactDeletePages(menus.MenuPages):
    def __init__(self, source, **kwargs):
        super().__init__(source, **kwargs)

    async def update(self, payload):
        if self._can_remove_reactions:
            if payload.event_type == 'REACTION_ADD':
                await self.bot.http.remove_reaction(
                    payload.channel_id, payload.message_id,
                    discord.Message._emoji_reaction(payload.emoji), payload.member.id
                )
            elif payload.event_type == 'REACTION_REMOVE':
                return
        await super().update(payload)

    def stop(self):
        loop = self.bot.loop
        loop.create_task(self.clear_buttons(react=True))
        super().stop()


class DynamicOptionMenu(menus.Menu):
    """Takes a number of arguments and parses them into a menu (for now, up to 9)"""

    def __init__(self, *options):
        if len(options) > 9:
            raise commands.CommandError(message="Too many arguments give, can be up to 9")

        self.options = options
        self.result = None

        self.numbers = {
            1: '\U00000031\U0000fe0f\U000020e3',
            2: '\U00000032\U0000fe0f\U000020e3',
            3: "\U00000033\U0000fe0f\U000020e3",
            4: "\U00000034\U0000fe0f\U000020e3",
            5: "\U00000035\U0000fe0f\U000020e3",
            6: "\U00000036\U0000fe0f\U000020e3",
            7: "\U00000037\U0000fe0f\U000020e3",
            8: "\U00000038\U0000fe0f\U000020e3",
            9: "\U00000039\U0000fe0f\U000020e3"
        }
        super().__init__(timeout=60.0)
        for num, o in enumerate(self.options, start=1):
            async def f(self, payload, *, num=num):
                self.result = num
                await self.clear_buttons(react=True)
                self.stop()

            self.add_button(menus.Button(self.numbers[num], action=f))

    async def send_initial_message(self, ctx, channel):
        """Send the inital message"""
        return await channel.send("Initial message")

    async def prompt(self, ctx):
        """Starts the menu"""
        await self.start(ctx, wait=True)
        return self.result


class MenuDeleteReacts(menus.Menu):
    """Menu that deletes reactions as it is used"""
    async def update(self, payload):
        if self._can_remove_reactions:
            if payload.event_type == 'REACTION_ADD':
                await self.bot.http.remove_reaction(
                    payload.channel_id, payload.message_id,
                    discord.Message._emoji_reaction(payload.emoji), payload.member.id
                )
            elif payload.event_type == 'REACTION_REMOVE':
                return
        await super().update(payload)

    def stop(self):
        self.bot.loop.create_task(self.clear_buttons(react=True))
        super().stop()


class MenuWizard(MenuDeleteReacts):
    """Menu that lets you make wizards"""

    async def wait_for_response(self):
        """Waits for a user to respond with text"""
        def check(message):
            return message.author == self.ctx.author and message.channel == self.ctx.channel

        try:
            msg = await self.bot.wait_for("message", timeout=60.0, check=check)

        except asyncio.TimeoutError:
            await self.ctx.send("Timed out")

        else:
            return msg

    async def ask_user(self):
        """Asks the user for input"""
        msg = None
        try:
            msg = await self.wait_for_response()
        except asyncio.TimeoutError:
            self.stop()
        if not msg:
            await self.ctx.send("Uh something went wrong you should not be seeing this!")
            self.stop()

        if not msg.attachments:
            try:
                self.ctx.bot.is_in_menu = True
                await msg.delete()
            except discord.Forbidden:
                pass
        return msg

    @menus.button("\N{CROSS MARK}")
    async def quit(self, payload):
        """Ends menu session"""
        self.stop()

