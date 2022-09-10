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
        emb_desc = get_bot_description(self.context)
        paginator = HelpPaginator(self.context, dict(mapping), 'bot', self, title="Help!", description=emb_desc,
                                  color=discord.Color.purple())

        # use a loop to stall
        await paginator.start()

    async def send_cog_help(self, cog: commands.Cog, /):
        """Sends cog help"""
        command_list = cog.get_commands()
        emb_desc = get_cog_description(self.context, cog)
        cog_paginator = HelpPaginator(self.context, command_list, "cog", self, title=f"Help for {cog.qualified_name}",
                                      description=emb_desc, color=discord.Color.purple())
        await cog_paginator.start()

    async def send_command_help(self, command: commands.Command[Any, ..., Any], /):
        """Sends command help"""
        if len(command.parents) == 0:
            emb_title = f"Help for `{command.name} {command.signature}`"
        else:
            parents = " ".join([c.name for c in command.parents])
            emb_title = f"Help for `{parents} {command.name} {command.signature}`"
        embed = discord.Embed(title=emb_title, description=command.short_doc,
                              colour=discord.Color.purple())

        if len(command.aliases) > 0:
            embed.add_field(name="Aliases", value=", ".join(command.aliases))
        await self.context.reply(embed=embed)

    async def send_group_help(self, group: commands.Group[Any, ..., Any], /) -> None:
        """Sends command group help"""
        group_commands = group.commands
        embed = discord.Embed(title=f"Help for `{group.name}`", description=group.short_doc, color=discord.Color.purple())
        val_str = ""
        for command in group_commands:
            val_str += f"""`{self.context.prefix}{command.name} {f"[{' | '.join(command.aliases)}]" if len(command.aliases) > 0 else ""}` - {command.short_doc}\n"""

        embed.add_field(name="Subcommands", value=val_str, inline=False)
        if len(group.aliases) > 0:
            embed.add_field(name="aliases", value=", ".join(group.aliases), inline=False)

        await self.context.reply(embed=embed)


class HelpPaginator(custom_views.BaseButtonPaginator):
    """Pagination over commands and cogs, clone of BtnPaginator with different formatting"""

    def __init__(self, ctx: commands.Context, entries: Union[list, dict], mode: str, help_cmd: TerryHelp,
                 **embed_properties):
        self.mode = mode
        self.help_cmd = help_cmd
        self.embed_properties = embed_properties
        cog_data = dict(zip(ctx.bot.cogs.keys(), [x.description for x in ctx.bot.cogs.values() if x]))
        self.dropdown = HelpSelect(cog_data)
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

    async def edit(self, new_entries: Union[list, dict], interaction: discord.Interaction, **embed_properties):
        """Updates a paginator's entries"""
        if isinstance(new_entries, dict):
            new_entries = custom_views.BaseButtonPaginator.process_dictionary(new_entries)
        self.entries = new_entries
        self.pages = self.create_pages(new_entries, self.per_page)
        embed = await self.format_page(entries=self._get_entries(index=self.min_page))
        embed.title = embed_properties['title']
        embed.description = embed_properties['description']
        await interaction.response.edit_message(embed=embed)


class HelpSelect(discord.ui.Select):
    """Control widget for help"""

    def __init__(self, cog_data: Dict[str, str], placeholder="What cog would you like help on?"):
        self.cog_data = cog_data  # name : description
        options = [
            discord.SelectOption(label="Main Help", value="mainhelp", description="See full bot help", emoji='🔍')]
        for name, description in cog_data.items():
            options.append(discord.SelectOption(label=name, value=name, description=description, emoji='🔍'))

        super().__init__(placeholder=placeholder, options=options, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        """Code to run for the drop-down"""
        cog_name = self.values[0]
        if cog_name == "mainhelp":
            self.view.mode = 'bot'
            help_cmd = self.view.help_cmd
            new_entries = dict(help_cmd.get_bot_mapping())
            emb_title = "Help!"
            emb_desc = get_bot_description(self.view.ctx)

        else:
            cog = self.view.ctx.bot.cogs[cog_name]
            self.view.mode = 'cog'
            new_entries = cog.get_commands()
            emb_title = f"Help for {cog_name}"
            emb_desc = get_cog_description(self.view.ctx, cog)

        await self.view.edit(new_entries, interaction, title=emb_title, description=emb_desc)


# util functions
def get_bot_description(context: commands.Context) -> str:
    """Gets Bot's description and prefix from invocation"""
    emb_desc = f"{context.bot.description}\n\nUse `{context.prefix}help [command]` for more information on a " \
               f"command.\nYou can also use `{context.prefix}help [category]` for more information on a category. "
    return emb_desc


def get_cog_description(context: commands.Context, cog: commands.Cog) -> str:
    """Gets a cog's description"""
    emb_desc = f"{cog.description}\nUse `{context.prefix}help [command]` for more information on a command."
    return emb_desc
