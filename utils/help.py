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
        print('a')
        cog_info = {}
        for cog in list(mapping):
            print(cog)
        print(mapping)

class HelpPaginator(custom_views.BaseButtonPaginator):
    """Pagination over commands and cogs, clone of BtnPaginator with different formatting"""

    def __init__(self, ctx: commands.Context, entries: Union[List[str], Dict[str, str]]):
        super().__init__(ctx, entries=entries, per_page=12)


class HelpSelect(discord.ui.Select):
    """Control widget for help"""

    def __init__(self, cog_data: Dict[str, str], placeholder="What module would you like help on?"):
        super().__init__(placeholder=placeholder)
        self.cog_data = cog_data  # name : description

    async def callback(self, interaction: discord.Interaction):
        """Code to run for the drop down"""
