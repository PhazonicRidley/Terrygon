import discord
from discord.ext import commands
import asyncio
from . import custom_views
from typing import Dict, Union, Any


# formatting inspired by rdanny and kurisu

class TerryHelp(commands.HelpCommand):
    """Custom help processing"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    async def send_bot_help(self, mapping, /):
        """Sends bot help"""
        emb_desc = f"{self.context.bot.description}\n\nUse `{self.context.prefix}help [command]` for more information on a command.\nYou can also use `{self.context.prefix}help [category]` for more information on a category."
        paginator = HelpPaginator(self.context, dict(mapping), 'bot', title="Help!", description=emb_desc,
                                  color=discord.Color.purple())

        # use a loop to stall
        await paginator.start()

    async def send_cog_help(self, cog: commands.Cog, /):
        """Sends cog help"""
        await create_cog_paginator(self.context, cog)

    async def send_command_help(self, command: commands.Command[Any, ..., Any], /):
        """Sends command help"""
        embed = discord.Embed(title=f"Help for {command.name}", description=command.short_doc, colour=discord.Color.purple())
        await self.get_destination().send(embed=embed)


class HelpPaginator(custom_views.BaseButtonPaginator):
    """Pagination over commands and cogs, clone of BtnPaginator with different formatting"""

    def __init__(self, ctx: commands.Context, entries: Union[list, dict], mode: str, **embed_properties):
        self.mode = mode
        self.embed_properties = embed_properties
        cog_data = dict(zip(ctx.bot.cogs.keys(), [x.description for x in ctx.bot.cogs.values() if x]))
        self.dropdown = HelpSelect(cog_data)
        self.switch_to_cog = None  # to be called in selector, terrible workaround for not nesting stack frames in
        # said selector function
        super().__init__(ctx, entries=entries, per_page=3)

    async def format_page(self, entries) -> discord.Embed:
        embed = discord.Embed(**self.embed_properties)  # TODO: make pretty later
        embed.set_footer(text=f"Page {self.current_page} of {self.total_pages}")
        if not entries:
            raise ValueError("No commands????????????????????")

        if self.mode == 'bot':
            for cog, command_list in entries:
                embed.add_field(name=f"__**{cog.qualified_name if cog else 'No Category'}**__",
                                value=f"{', '.join([f'`{x.name}`' for x in command_list])}", inline=False)

        elif self.mode == 'cog':
            for command in entries:
                # TODO: fix formatting
                embed.add_field(name=f"__**{command.name}**__",
                                value=command.short_doc if command.short_doc else "No description", inline=False)

        return embed

    async def start(self, *, message: discord.Message = None, have_select=True) -> (discord.Message, str or None):
        """Starts paginator"""
        if have_select:
            self.add_item(self.dropdown)
        await super().start(message=message)
        return self.ctx.message, self.switch_to_cog  # prob not an amazing way of doing this


class HelpSelect(discord.ui.Select):
    """Control widget for help"""

    def __init__(self, cog_data: Dict[str, str], placeholder="What cog would you like help on?"):
        self.cog_data = cog_data  # name : description
        options = []
        for name, description in cog_data.items():
            options.append(discord.SelectOption(label=name, value=name, description=description, emoji='🔍'))

        super().__init__(placeholder=placeholder, options=options, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        """Code to run for the drop-down"""
        cog_name = self.values[0]
        await create_cog_paginator(self.view.ctx, cog_name)
        await self.view.stop_paginator(interaction, to_delete_msg=True)


async def create_cog_paginator(ctx: commands.Context, cog: Union[commands.Cog, str]):
    """Creates and runs the cog paginator"""
    if isinstance(cog, str):
        cog = ctx.bot.cogs[cog]

    if cog is None:
        raise AttributeError("Invalid cog passed.")

    command_list = cog.get_commands()
    emb_desc = f"{cog.description}\nUse `{ctx.prefix}help [command]` for more information on a command."
    cog_paginator = HelpPaginator(ctx, command_list, "cog", title=f"Help for {cog.qualified_name}",
                                  description=emb_desc, color=discord.Color.purple())
    await cog_paginator.start(have_select=False)
