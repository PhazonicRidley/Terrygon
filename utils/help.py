import discord
from discord.ext import commands

from . import custom_views
from typing import Dict, Union, List, Mapping, Optional


# formatting inspired by rdanny and kurisu

class TerryHelp(commands.HelpCommand):
    """Custom help processing"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    async def send_bot_help(self, mapping, /):
        """Sends bot help"""

        paginator = HelpPaginator(self.context, list(mapping), 'bot')
        await paginator.start()


class HelpPaginator(custom_views.BaseButtonPaginator):
    """Pagination over commands and cogs, clone of BtnPaginator with different formatting"""

    def __init__(self, ctx: commands.Context, entries: Union[List[str], Dict[str, str]], mode: str):
        self.mode = mode
        self.prefix = ctx.prefix
        # self.select =
        super().__init__(ctx, entries=entries, per_page=3)

    async def format_page(self, entries) -> discord.Embed:
        embed = discord.Embed(title="Help!")  # TODO: make pretty later
        embed.set_footer(text=f"Page {self.current_page} of {self.total_pages}")
        if not entries:
            raise ValueError("You prob made a mistake.")

        if self.mode == 'bot':
            # TODO: get paginator to handle dicts properly in _format_entries. split the dict up have a list of dicts
            for cog in entries:
                embed.add_field(name=f"__**{cog.qualified_name}**__",
                                value=f"{'  '.join([x.name for x in cog.get_commands()])}", inline=False)

        return embed


class HelpSelect(discord.ui.Select):
    """Control widget for help"""

    def __init__(self, cog_data: Dict[str, str], placeholder="What module would you like help on?"):
        super().__init__(placeholder=placeholder)
        self.cog_data = cog_data  # name : description

    async def callback(self, interaction: discord.Interaction):
        """Code to run for the drop down"""
