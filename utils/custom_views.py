# requires discord.py 2.0
import discord
from discord.ext import commands
from typing import List, Generator, Any, TYPE_CHECKING, Union, Dict


class BaseButtonPaginator(discord.ui.View):
    """
    Modified from: https://gist.github.com/NextChai
    The Base Button Paginator class. Will handle all page switching without
    you having to do anything.
    
    Attributes
    ----------
    entries: List[Any]
        A list of entries to get spread across pages.
    per_page: :class:`int`
        The number of entries that get passed onto one page.
    pages: List[List[Any]]
        A list of pages which contain all entries for that page.
    """

    def __init__(self, ctx: commands.Context, *, entries: Union[List[Any], Dict[Any, Any]], per_page: int = 6) -> None:
        super().__init__(timeout=180)
        if isinstance(entries, list):
            self.entries = entries
        else:
            self.entries = BaseButtonPaginator.process_dictionary(entries)
        self.per_page = per_page
        self.ctx = ctx
        self._min_page = 1
        self._current_page = 1
        self.pages = list(self._format_pages(self.entries, per_page))
        self._max_page = len(self.pages)
    
    @classmethod
    def process_dictionary(cls, entries: dict[Any, Any]) -> list[tuple]:
        """Splits a dictionary to be wrapped by a list"""
        return list(zip(entries.keys(), entries.values()))

    @property
    def max_page(self) -> int:
        """:class:`int`: The max page count for this paginator."""
        return self._max_page

    @property
    def min_page(self) -> int:
        """:class:`int`: The min page count for this paginator."""
        return self._min_page

    @property
    def current_page(self) -> int:
        """:class:`int`: The current page the user is on."""
        return self._current_page

    @property
    def total_pages(self) -> int:
        """:class:`int`: Returns the total amount of pages."""
        return len(self.pages)

    async def format_page(self, entries: Union[List[Any], Dict[Any, Any]]) -> discord.Embed:
        """|coro|
        Used to make the embed that the user sees.
        
        Parameters
        ----------
        entries: Union[List[Any], Dict[Any, Any]]
            A list of entries for the current page.
           
        Returns
        -------
        :class:`discord.Embed`
            The embed for this page.
        """
        raise NotImplementedError('Subclass did not overwrite format_page coro.')

    def _format_pages(self, entries, per_page) -> Generator[List[Any], None, None]:
        for i in range(0, len(entries), per_page):
            yield entries[i:i + per_page]

    def _get_entries(self, *, up: bool = True, increment: bool = True, index: int = None) -> List[Any]:
        if increment:
            if up:
                self._current_page += 1
                if self._current_page > self._max_page:
                    self._current_page = self._min_page
            else:
                self._current_page -= 1
                if self._current_page < self._min_page:
                    self._current_page = self.max_page
        elif index:
            if 1 > index >= self._current_page:
                raise commands.BadArgument("Invalid page index passed")

            self._current_page = index
        return self.pages[self._current_page - 1]

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """makes sure only the context user can activate interactions"""
        if interaction.user == self.ctx.author:
            return True

        await interaction.response.send_message(f"This menu can only be controlled by {self.ctx.author}", ephemeral=True)
        return False

    def get_page(self, idx: int) -> List[Any]:
        """Gets a page from the paginator"""
        return self.pages[idx - 1]

    def set_page(self, idx: int):
        """Sets a page"""
        if 1 > idx >= self._current_page:
            raise commands.BadArgument("Invalid page index passed")
        self._current_page = idx

    @discord.ui.button(emoji='\U000023ea', style=discord.ButtonStyle.gray)
    async def on_rewind(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        # TODO: fix
        entries = self._get_entries(index=self.min_page)
        embed = await self.format_page(entries=entries)
        return await interaction.response.edit_message(embed=embed)

    @discord.ui.button(emoji='\U000025c0', style=discord.ButtonStyle.blurple)
    async def on_arrow_backward(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        entries = self._get_entries(up=False)
        embed = await self.format_page(entries=entries)
        return await interaction.response.edit_message(embed=embed)

    @discord.ui.button(emoji='\U000025b6', style=discord.ButtonStyle.blurple)
    async def on_arrow_forward(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        entries = self._get_entries(up=True)
        embed = await self.format_page(entries=entries)
        return await interaction.response.edit_message(embed=embed)

    @discord.ui.button(emoji='\U000023e9', style=discord.ButtonStyle.gray)
    async def on_fastforward(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        # TODO: fix
        entries = self._get_entries(index=self.max_page)
        embed = await self.format_page(entries=entries)
        return await interaction.response.edit_message(embed=embed)

    @discord.ui.button(emoji='\U000023f9', style=discord.ButtonStyle.red)
    async def on_stop(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.clear_items()
        self.stop()
        return await interaction.response.edit_message(view=self)

    async def start(self):
        """|coro|
        
        Used to start the paginator.
        """
        entries = self._get_entries(increment=False)
        embed = await self.format_page(entries=entries)
        await self.ctx.send(embed=embed, view=self)


class PaginatorSelector(discord.ui.Select):
    """A select menu for jumping to different pages"""
    def __init__(self, pages: List[Any]):
        # create selector options
        options = []
        descriptions = []
        for page in pages:
            first_three = page[:3]
            desc = ", ".join([''.join(filter(str.isalnum, str(s))) for s in first_three]) + "..."
            if len(desc) > 53:
                desc = desc[:50] + "..."
            descriptions.append(desc)

        for idx, p in enumerate(descriptions, start=1):
            options.append(discord.SelectOption(label=str(idx), value=str(idx), description=p))

        super().__init__(placeholder="What page?", options=options, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        """Driving code"""
        entries = self.view.get_page(int(self.values[0]))
        embed = await self.view.format_page(entries=entries)
        embed.set_footer(text=f"Page {self.values[0]} of {self.view.total_pages}")
        self.view.set_page(int(self.values[0]))
        return await interaction.response.edit_message(embed=embed)


# Can be used as so
class BtnPaginator(BaseButtonPaginator):
    def __init__(self, ctx: commands.Context, entries: Union[List[Any], Dict[Any, Any]], *, per_page: int = 6, **embed_properties):
        super().__init__(ctx, entries=entries, per_page=per_page)
        self.embed_properties = embed_properties
        self.add_item(PaginatorSelector(self.pages))

    async def format_page(self, entries) -> discord.Embed:
        embed = discord.Embed(**self.embed_properties)
        embed.set_footer(text=f"Page {self.current_page} of {self.total_pages}")
        if entries:
            embed.description = ""
            for entry in entries:
                embed.description += f"{entry}\n"
        else:
            embed.description = "No entries"

        return embed


class Confirmation(discord.ui.View):
    def __init__(self, confirm_text: str, cancel_text: str):
        super().__init__(timeout=180)
        self.confirm_text = confirm_text
        self.cancel_text = cancel_text
        self.value = None

    @discord.ui.button(emoji="\U00002714️", style=discord.ButtonStyle.green)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = True
        self.clear_items()
        self.stop()
        await interaction.response.edit_message(content=self.confirm_text, view=self)

    @discord.ui.button(emoji="\U00002716️", style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.clear_items()
        self.value = False
        self.stop()
        return await interaction.response.edit_message(content=self.cancel_text, view=self)


