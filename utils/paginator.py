import discord
from discord.ext import menus


# BasicEmbedCommand taken from https://gitlab.com/lightning-bot/Lightning/-/blob/v3/utils/menus.py#L21
# GPLv3 Licensed - Copyright (c) 2020 - LightSage
class BasicEmbedMenu(menus.ListPageSource):
    def __init__(self, data, *, per_page, embed=None):
        self.embed = embed
       # self.embedoptions = embedoptions
        super().__init__(data, per_page=per_page)

    async def format_page(self, menu, entries):
        if self.embed:
            embed = self.embed
        else:
            embed = discord.Embed(color=discord.Color.greyple())
        embed.description = "\n".join(entries)
        #embed.add_field(name="I wont change", value="UNTIL ITS OVERRRR!!!")
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
        loop.create_task(self.message.delete())
        super().stop()
