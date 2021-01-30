import asyncio
import re
import aiohttp
import discord
import typing
import webcolors
from discord.ext import commands, menus
from utils import paginator, common


class CustomCommands(commands.Cog):
    """ Custom command system
    """

    # TODO: add a subcommand system.

    def __init__(self, bot):
        self.bot = bot
        asyncio.create_task(self.get_custom_commands())

    async def get_custom_commands(self):
        """Puts all existing custom commands into the bot"""
        custom_commands = await self.bot.db.fetch(
            "SELECT DISTINCT name, description, aliases, tags, id FROM custom_commands")
        for command in custom_commands:

            if command.get("tags") and "SUBCOMMAND" in command.get("tags"):
                continue

            aliases = command['aliases']
            if not aliases:
                aliases = []

            if command.get("tags") and "SUBCOMMANDHEAD" in command.get("tags"):
                # handle all subcommands
                subcmd_head = await self.make_subcommand_head(command['name'], command['description'], aliases)
                subcmds = await self.bot.db.fetch("SELECT * FROM custom_commands WHERE head_id = $1", command['id'])
                for subcmd in subcmds:
                    await self.make_subcommand(subcmd_head, subcmd['name'], subcmd.get("description"),
                                               subcmd.get("aliases"))
            else:
                # handle regular custom commands
                await self.add_custom_command(command['name'], command['description'], aliases)

    async def add_custom_command(self, name, description, aliases=None):
        """adds a custom command to the bot"""

        if aliases is None:
            aliases = []

        @commands.command(name=name, help=description, aliases=aliases)
        async def cmd(self, ctx):
            cmd_output = await self.bot.db.fetchrow(
                "SELECT output, embed_dicts FROM custom_commands WHERE name = $1 AND guild_id = $2", ctx.command.name,
                ctx.guild.id)
            if not cmd_output:
                return
            msg_content = cmd_output.get("output")
            emb_dict = cmd_output.get('embed_dicts')
            emb = None
            if emb_dict:
                emb = discord.Embed.from_dict(emb_dict)
            await ctx.send(content=msg_content, embed=emb)

        cmd.cog = self
        self.__cog_commands__ = self.__cog_commands__ + (cmd,)
        self.bot.add_command(cmd)

    async def make_subcommand_head(self, name, description, aliases=None):
        """Makes a subcommand head"""
        if not aliases:
            aliases = []

        @commands.group(name=name, help=description, aliases=aliases, invoke_without_command=True)
        async def cmd_head(self, ctx):
            cmd_output = await self.bot.db.fetchrow(
                "SELECT output, embed_dicts FROM custom_commands WHERE name = $1 AND guild_id = $2", ctx.command.name,
                ctx.guild.id)
            if not cmd_output.get("output") and not cmd_output.get("embed_dicts"):
                await ctx.send_help(ctx.command)
            else:
                msg_content = cmd_output.get("output")
                emb_dict = cmd_output.get("embed_dicts")
                emb = None
                if emb_dict:
                    emb = discord.Embed.from_dict(emb_dict)
                await ctx.send(content=msg_content, embed=emb)

        cmd_head.cog = self
        self.__cog_commands__ = self.__cog_commands__ + (cmd_head,)
        self.bot.add_command(cmd_head)
        return cmd_head

    async def make_subcommand(self, cmd_head: typing.Union[str, commands.group], name, description, aliases=None):
        """Makes a subcommand"""
        if isinstance(cmd_head, str):
            cmd_head = self.bot.get_command(cmd_head)
            if not cmd_head:
                raise commands.CommandNotFound(message="Unknown command!")

        if not aliases:
            aliases = []

        @cmd_head.command(name=name, help=description, aliases=aliases)
        async def sub_cmd(self, ctx):
            subhead_id = await self.bot.db.fetchval(
                "SELECT id FROM custom_commands WHERE name = $1 AND guild_id = $2 AND 'SUBCOMMANDHEAD' = ANY(tags)",
                ctx.command.parent.name, ctx.guild.id)
            cmd_info = await self.bot.db.fetchrow(
                "SELECT output, embed_dicts FROM custom_commands WHERE head_id = $1 AND guild_id = $2 AND name = $3",
                subhead_id, ctx.guild.id, ctx.command.name)
            msg_content = cmd_info.get("output")
            emb_dict = cmd_info.get("embed_dicts")
            emb = None
            if emb_dict:
                emb = discord.Embed.from_dict(emb_dict)

            await ctx.send(content=msg_content, embed=emb)

        sub_cmd.cog = self
        self.__cog_commands__ = self.__cog_commands__ + (sub_cmd,)

    @commands.group(name="customcommands", invoke_without_command=True)
    async def custom_commands(self, ctx):
        """Handles guild's custom commands"""
        await ctx.send_help(ctx.command)

    @custom_commands.command(name="add", aliases=['update'])
    async def add(self, ctx, name):
        """Adds a new custom command or updates an existing custom command"""
        # First check if there's a custom command with that name already
        name = name.lower()
        embed_maker = CustomEmbedMenu()
        wizard = await CustomCommandWizard(embed_maker).make_command(ctx)
        existing_command = await self.bot.db.fetchval("SELECT name FROM custom_commands WHERE name = $1", name)
        # Check if there's a built in command, we don't want to override that
        if existing_command is None and ctx.bot.get_command(name):
            return await ctx.send(f"A built in command with the name {name} is already registered")

        tags = await self.bot.db.fetchval("SELECT tags FROM custom_commands WHERE name = $1 AND  guild_id = $2", name,
                                          ctx.guild.id)
        subhead = None
        if not tags or "SUBCOMMANDHEAD" not in tags:
            subhead, msg = await paginator.YesNoMenu("Would you like to make this a sub command head?").prompt(ctx)
            if subhead:
                wizard['tags'] = ["SUBCOMMANDHEAD"]
                await msg.edit(content="This is now a subcommand head")
            else:
                wizard['tags'] = []

        if not subhead and not wizard.get("content") and not wizard.get("embed"):
            return await ctx.send("Cannot make a blank command")

        if not wizard.get("description"):
            if subhead:
                wizard['description'] = "A cool sub command head."
            else:
                wizard["description"] = "A cool custom command."

        c = await self.bot.db.fetchrow(
            "SELECT id, tags FROM custom_commands WHERE name = $1 AND guild_id = $2 AND ('SUBCOMMAND' != ANY(tags) OR tags IS NULL)",
            name, ctx.guild.id)
        if not c:
            await self.bot.db.execute(
                "INSERT INTO custom_commands (name, guild_id, output, embed_dicts, description, tags) VALUES ($1, $2, $3, $4, $5, $6)",
                name, ctx.guild.id, wizard.get("content"), wizard.get("embed"), wizard.get("description"),
                wizard.get("tags"))
            await ctx.send(f"Added a command called {name}")

        else:
            await self.bot.db.execute(
                "UPDATE custom_commands SET output = $1, embed_dicts = $2 , description = $3 WHERE guild_id = $4 AND name = $5",
                wizard.get("content"), wizard.get("embed"), wizard['description'], ctx.guild.id, name)

            if 'SUBCOMMANDHEAD' in wizard['tags'] and 'SUBCOMMANDHEAD' not in c['tags']:
                await self.bot.db.execute("UPDATE custom_commands SET tags = array_append(tags, $1) WHERE id = $2",
                                          wizard['tags'], c['id'])
            elif 'SUBCOMMANDHEAD' not in wizard['tags'] and 'SUBCOMMANDHEAD' in c['tags']:
                await self.bot.db.execute(
                    "UPDATE custom_commands SET tags = array_remove(tags, 'SUBCOMMANDHEAD') WHERE id = $1", c['id'])

            self.bot.reload_extension(__name__)
            await ctx.send(f"Updated {name}")

        if not existing_command:
            if not subhead:
                await self.add_custom_command(name, wizard.get("description"))
            else:
                await self.make_subcommand_head(name, wizard.get("description"))

    @custom_commands.command(name="appendsubcommand", aliases=['addsub', 'addsubcommand'])
    async def append_subcmd(self, ctx, head_name, name):
        """Adds a subcommand to an existing subcommand head"""
        head_dict = await self.bot.db.fetchrow(
            "SELECT * FROM custom_commands WHERE name = $1 AND guild_id = $2 AND 'SUBCOMMANDHEAD' = ANY(tags)",
            head_name, ctx.guild.id)
        if not head_dict:
            return await ctx.send("Following command either doesn't exist or is not a subcommand head!")

        name = name.lower()
        embed_maker = CustomEmbedMenu()
        wizard = await CustomCommandWizard(embed_maker).make_command(ctx)
        existing_command = await self.bot.db.fetchval("SELECT name FROM custom_commands WHERE name = $1", name)
        # Check if there's a built in command, we don't want to override that
        if existing_command is None and ctx.bot.get_command(name):
            return await ctx.send(f"A built in command with the name {name} is already registered")

        if not wizard.get("content") and not wizard.get("embed"):
            return await ctx.send("Cannot make a blank command")

        if not wizard.get("description"):
            wizard['description'] = "A cool sub command."

        if not await self.bot.db.fetchval(
                "SELECT id FROM custom_commands WHERE name = $1 AND guild_id = $2 AND head_id = $3", name, ctx.guild.id,
                head_dict['id']):
            await self.bot.db.execute(
                "INSERT INTO custom_commands (name, guild_id, output, embed_dicts, description, tags, head_id) VALUES ($1, $2, $3, $4, $5, $6, $7)",
                name, ctx.guild.id, wizard.get("content"), wizard.get("embed"), wizard.get("description"),
                ['SUBCOMMAND'], head_dict['id'])
            await ctx.send(f"Added a subcommand to {head_name} called {name}")

        else:
            await self.bot.db.execute(
                "UPDATE custom_commands SET output = $1, embed_dicts = $2 , tags = array_append(tags, $3), description = $4 WHERE guild_id = $5 AND name = $6 AND head_id = $7",
                wizard.get("content"), wizard.get("embed"), ['SUBCOMMAND'], wizard['description'], ctx.guild.id, name,
                head_dict['id'])

            self.bot.reload_extension(__name__)
            await ctx.send(f"Updated {name}")

        subcmd_head = self.bot.get_command(head_name)
        await self.make_subcommand(subcmd_head, name, wizard.get("description"))

    @custom_commands.command(name="remove", aliases=['del'])
    async def remove(self, ctx, name):
        """Removes a custom command"""
        # Make sure it's actually a custom command, to avoid removing a real command
        command_row = await self.bot.db.fetchrow(
            "SELECT * FROM custom_commands WHERE guild_id = $1 AND name = $2 AND ('SUBCOMMAND' != ANY(tags) OR tags IS NULL)",
            ctx.guild.id, name)
        if not command_row:
            return await ctx.send(f"There is no custom command called {name}")
        elif 'SUBCOMMANDHEAD' in command_row.get('tags'):
            # check if head has subcommands attached
            subcommands = await self.bot.db.fetch("SELECT id FROM custom_commands WHERE head_id = $1 AND guild_id = $2",
                                                  command_row['id'], ctx.guild.id)
            if len(subcommands) != 0:
                res, msg = await paginator.YesNoMenu(
                    "Would you like to delete all the subcommands that are apart of this header?").prompt(ctx)
                if res:
                    for cid in subcommands:
                        await self.bot.db.execute("DELETE FROM custom_commands WHERE id = $1", cid)

                    await msg.edit(content="All subcommands deleted")
                else:
                    await msg.edit(content="subcommands not deleted, cannot delete header with subcommands attached!")
                    return

        # deletes the command
        await self.bot.db.execute("DELETE FROM custom_commands WHERE name = $1 AND guild_id = $2", name, ctx.guild.id)
        await ctx.send(f"Removed a command called {name}")
        self.bot.reload_extension(__name__)

    @custom_commands.command(name="removesubcmd", aliases=['delsubcmd', 'delsub'])
    async def remove_subcommand(self, ctx, head_name, sub_name):
        """Removes a subcommand from a head"""
        head_dict = await self.bot.db.fetchrow(
            "SELECT * FROM custom_commands WHERE name = $1 AND guild_id = $2 AND 'SUBCOMMANDHEAD' = ANY(tags)",
            head_name, ctx.guild.id)
        if not head_dict:
            return await ctx.send("Following command either doesn't exist or is not a subcommand head!")

        subcmd_id = await self.bot.db.fetchval(
            "SELECT id FROM custom_commands WHERE head_id = $1 AND name = $2 AND guild_id = $3 AND 'SUBCOMMAND' = ANY(tags)",
            head_dict['id'], sub_name, ctx.guild.id)
        if not subcmd_id:
            return await ctx.send(f"The command `{head_name}` does not have a subcommand called `{sub_name}`")

        # delete the sub command
        await self.bot.db.execute("DELETE FROM custom_commands WHERE id = $1", subcmd_id)
        await ctx.send(f"Removed subcommand `{sub_name}`")
        self.bot.reload_extension(__name__)

    @commands.group(name="aliases", invoke_without_command=True)
    async def aliases(self, ctx):
        """Alias management commands"""
        await ctx.send_help(ctx.command)

    @aliases.command(name="add")
    async def add_alias(self, ctx, cmd_name, alias):
        """Adds an alias to a command"""
        cmd_dict = await self.bot.db.fetchrow(
            "SELECT id, aliases FROM custom_commands WHERE name = $1 AND guild_id = $2", cmd_name, ctx.guild.id)
        if not cmd_dict:
            return await ctx.send(f"No custom command called `{cmd_name}` on this server!")

        if not cmd_dict['aliases'] or alias not in cmd_dict['aliases'] and not self.bot.get_command(alias):
            await self.bot.db.execute(
                "UPDATE custom_commands SET aliases = array_append(aliases, $1) WHERE id = $2",
                alias, cmd_dict['id'])
        else:
            return await ctx.send(
                f"Alias already saved to `{cmd_name}` or bot already has a base command by this alias.")

        await ctx.send("Alias saved!")
        self.bot.reload_extension(__name__)

    @aliases.command(name="remove", aliases=['del'])
    async def remove_alias(self, ctx, cmd_name, alias):
        """Removes an alias from a custom command"""
        cmd_dict = await self.bot.db.fetchrow(
            "SELECT id, name, aliases FROM custom_commands WHERE name = $1 AND guild_id = $2", cmd_name, ctx.guild.id)
        if not cmd_dict:
            return await ctx.send(f"No custom command called `{cmd_name}` on this server!")

        if not cmd_dict['aliases'] or alias not in cmd_dict['aliases']:
            return await ctx.send(f"No alias called `{alias}` on the command `{cmd_name}`")
        else:
            await self.bot.db.execute("UPDATE custom_commands SET aliases = array_remove(aliases, $1) WHERE id = $2",
                                      alias, cmd_dict['id'])
            await ctx.send("Alias removed!")
            self.bot.reload_extension(__name__)

    @commands.command()
    async def test(self, ctx):
        menu = CustomEmbedMenu()
        embed_dict = await menu.get_embed(ctx)
        await ctx.send(f"```{embed_dict}```")


class CustomCommandWizard(paginator.MenuWizard):
    """Wizard for making custom commands"""

    def __init__(self, embed_maker):
        super().__init__(timeout=300.0)
        self.embed_maker = embed_maker
        self.command_data = dict()

    async def make_command(self, ctx):
        """Makes the command"""
        await self.start(ctx, wait=True)
        return self.command_data

    async def send_initial_message(self, ctx, channel):
        emb = discord.Embed(title="Welcome to the interactive custom command wizard",
                            description="To get started click the reactions below. Need help using this wizard? click the question mark.",
                            color=discord.Color.blurple())
        return await channel.send(embed=emb)

    @menus.button("\N{BLACK QUESTION MARK ORNAMENT}")
    async def menu_help(self, payload):
        """Shows help for the menu"""
        emb = discord.Embed(title="Menu help", color=discord.Color.blurple())
        emb.add_field(name=":file_folder: Message content", value="Sets message content", inline=False)
        emb.add_field(name=":paperclips: Custom embed", value="Make your own custom embed", inline=False)
        emb.add_field(name=":notepad_spiral: Command Description", value="Set a description for your custom command")
        await self.message.edit(embed=emb)

    @menus.button("\N{FILE FOLDER}")
    async def content(self, payload):
        """Adds text content to the custom command"""
        await self.message.edit(content="Type what you want the content of your command to be (`q` to quit)")
        ret = await self.ask_user()
        ret = ret.content
        if ret == "q":
            await self.message.edit(content="Exiting.....")
            return

        await self.message.edit(content="Success!")
        self.command_data['content'] = ret

    @menus.button("\N{LINKED PAPERCLIPS}")
    async def embed(self, payload):
        """Sets the embed for a custom command"""
        emb_dict = await self.embed_maker.get_embed(self.ctx)
        await self.message.edit(content="Success!")
        self.command_data['embed'] = emb_dict

    @menus.button("\N{SPIRAL NOTE PAD}")
    async def set_description(self, payload):
        """Sets the description for a custom command"""
        await self.message.edit(content="Type what you want the description of your command to be (`q` to quit)")
        ret = await self.ask_user()
        ret = ret.content
        if ret == "q":
            await self.message.edit(content="Exiting.....")
            return

        await self.message.edit(content="Success!")
        self.command_data['description'] = ret


# loosely based off of a project by LightSage <repo link here>
async def check_url_image(url):
    """Checks a url to see if it is an image"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                headers = resp.headers

        if not resp.headers['Content-Type'].startswith('image'):
            raise aiohttp.InvalidURL(url=url)
    except aiohttp.InvalidURL:
        return False

    return True


class CustomEmbedMenu(paginator.MenuWizard):
    """Handles embed creation in a nice user interface"""

    def __init__(self):
        super().__init__(timeout=60.0)
        self.custom_embed = discord.Embed()

    async def send_initial_message(self, ctx, channel):
        emb = discord.Embed(title="Embed builder", color=discord.Color.red())
        emb.description = "Welcome to the interactive custom embed wizard. React below on things to add to your embed. react with \U00002753 for more information about the various options"
        return await channel.send(embed=emb)

    async def get_embed(self, ctx):
        await self.start(ctx, wait=True)
        return self.custom_embed.to_dict()

    # menu options
    @menus.button("\N{BLACK QUESTION MARK ORNAMENT}")
    async def menu_info(self, payload):
        """Shows information about the bot"""
        prompt_embed = discord.Embed(title="Information about this wizard",
                                     description="Below is information on how to use this wizard",
                                     color=discord.Color.blurple())
        prompt_embed.add_field(name=":label: Title", value="The title of the embed", inline=False)
        prompt_embed.add_field(name=":notebook: Description",
                               value="The description of the embed, shown under the title", inline=False)
        prompt_embed.add_field(name=":art: Color",
                               value="The embed's color. This can either be a hex or a discord color.", inline=False)
        prompt_embed.add_field(name=":frame_photo: Image",
                               value="An embed's image. This can either be an attachment or a link to an image",
                               inline=False)
        prompt_embed.add_field(name=":card_index: Thumbnail",
                               value="The thumbnail image of an embed. This can either be an image or a link to an image",
                               inline=False)
        prompt_embed.add_field(name=":grinning: Author",
                               value="Triggers the author wizard. You will need to give a name and optionally a link and a profile picture.",
                               inline=False)
        prompt_embed.add_field(name=":pencil: Add Field",
                               value="An embed field. You will need to give a name, value, and if you would like it embedded or not. You can have multiple of these",
                               inline=False)

        prompt_embed.add_field(name=":man_gesturing_no: Remove Field", value="Removes a field from the embed.",
                               inline=False)

        prompt_embed.add_field(name=":footprints: Footer", value="The footer of an embed", inline=False)

        prompt_embed.add_field(name="\U000023ef Preview embed", value="Shows current embed that is being made")

        await self.message.edit(embed=prompt_embed)

    @menus.button("\N{LABEL}")
    async def set_title(self, payload):
        """Sets the title"""
        await self.message.edit(content="Type what you want your embed's title to be. (`q` to quit)")
        ret = await self.ask_user()
        ret = ret.content
        if ret.lower() == 'q':
            await self.message.edit(content="Exiting to main menu.....")
            return
        self.custom_embed.title = ret

        await self.message.edit(content="Success!")

    @menus.button("\N{NOTEBOOK}")
    async def set_description(self, payload):
        """Set the description"""
        await self.message.edit(content="Type what you want your embed's description to be (`q` to quit)")
        ret = await self.ask_user()
        ret = ret.content
        if ret.lower() == 'q':
            await self.message.edit(content="Exiting to main menu.....")
            return
        self.custom_embed.description = ret

        await self.message.edit(content="Success")

    @menus.button("\N{GRINNING FACE}")
    async def set_author(self, payload):
        """Set the author"""
        author_data = {}
        progress_embed = discord.Embed(title="Author wizard progress", color=discord.Color.blurple())
        # author's name
        await self.message.edit(content="Type the name of the author (type `q` to cancel)")
        while True:
            name = await self.ask_user()
            name = name.content
            if not name:
                await self.message.edit(content="Please enter text for the name of the author. (type `q` to cancel)")
                await asyncio.sleep(2)
                continue

            elif name.lower() == 'q':
                await self.message.edit(content="Returning to main menu....")
                return

            if len(name) > 256:
                await self.message.edit(content="Cannot set name, too long! (type `q` to cancel)")
                continue

            author_data.update({'name': name})
            progress_embed.add_field(name="Name", value=f"`{name}`")
            await self.message.edit(embed=progress_embed)
            break

        # author's url
        await self.message.edit(
            content="Type the url you want the author's name to link to (type `skip` to skip or `q` to return to the main menu)")
        while True:
            url = await self.ask_user()
            url = url.content
            if url.lower() == 'skip':
                await self.message.edit(content="Skipping...")
                url = None
                break
            elif url.lower() == 'q':
                await self.message.edit(content="Returning to the main menu....")
                return

            try:
                async with aiohttp.ClientSession() as session:
                    await session.get(url)
                    await self.message.edit(content="Valid url")

            except aiohttp.InvalidURL:
                await self.message.edit(
                    content="Invalid url, please try again (type `skip` to skip or `q` to return to the main menu)")
                continue

            author_data.update({'url': url})
            progress_embed.add_field(name="URL", value=f"{url}", inline=False)
            await self.message.edit(embed=progress_embed)
            break

        # author's icon
        await self.message.edit(
            content="Upload an image or give a url to an image to use as the avatar icon. (type `skip` to skip or `q` to quit)")
        while True:
            icon_msg = await self.ask_user()
            if icon_msg.content.lower() == "q":
                await self.message.edit(content="Exiting to main menu....")
                return

            elif icon_msg.content.lower() == 'skip':
                await self.message.edit(content="Skipping....")
                break

            if icon_msg.attachments:
                # only take the first attachment
                icon = icon_msg.attachments[0].url
            else:
                icon = icon_msg.content

            # check to make sure the url is an image
            if not await check_url_image(icon):
                await self.message.edit(
                    content="Invalid url or attachment. It must be an image! (type `skip` to skip or `q` to quit)")
                continue

            author_data.update({'icon_url': icon})
            progress_embed.add_field(name="icon url", value=f"{icon}", inline=False)
            progress_embed.set_thumbnail(url=icon)
            await self.message.edit(embed=progress_embed)
            break

        # put the author together
        try:
            self.custom_embed.set_author(**author_data)
        except discord.HTTPException:
            return await self.message.edit(content="Cannot create author, please try again")

        await self.message.edit(content="Success!")

    @menus.button("\N{ARTIST PALETTE}")
    async def set_color(self, payload):
        """Sets the embed's color"""
        await self.message.edit(
            content="Type the discord color or the hex you would like your embed to have. (`q` to quit)")
        while True:
            ret = await self.ask_user()
            ret = ret.content
            if ret.lower() == 'q':
                await self.message.edit(content="Exiting colors....")
                return

            # lets parse the color first
            discord_colors = {}
            for method in dir(discord.Color):
                if method.startswith("_") or method.startswith('from') or (len(method)) == 1 or method == 'value':
                    continue

                if not isinstance(color := getattr(discord.Color, method), property):
                    discord_colors[method] = color

            ret = ret.replace(" ", "_")

            if ret.lower() in discord_colors.keys():
                color = discord_colors[ret]()
                break

            color = ret
            if color[0] != "#":
                color = "#" + color

            if len(color) != 7:
                await self.message.edit(
                    content="Invalid color option given, please try again. Valid options are either a discord color or a color hex. or type `q` to exit")
                continue

            color = discord.Color.from_rgb(*webcolors.hex_to_rgb(color))
            break

        # stupid hacky workaround for this
        d = self.custom_embed.to_dict()
        d['color'] = color.value
        self.custom_embed = discord.Embed.from_dict(d)
        await self.message.edit(content="Success!")

    @menus.button("\N{CARD INDEX}")
    async def set_thumbnail(self, payload):
        """Sets the thumbnail"""
        await self.message.edit(
            content="Upload a picture post a link to a picture to set as the embed's thumbnail. (`q` to quit)")
        while True:
            msg = await self.ask_user()
            if msg.content.lower() == 'q':
                await self.message.edit(content="Exiting to main menu...")
                return

            if msg.attachments:
                thumbnail = msg.attachments[0].url
            else:
                thumbnail = msg.content

            if not await check_url_image(thumbnail):
                await self.message.edit(content="Invalid image given, please try again (`q` to quit)")
                continue

            break

        self.custom_embed.set_thumbnail(url=thumbnail)
        await self.message.edit(content="Success!")

    @menus.button("\N{FRAME WITH PICTURE}")
    async def set_image(self, payload):
        """Set image"""
        await self.message.edit(
            content="Upload a picture post a link to a picture to set as the embed's image. (`q` to quit)")
        while True:
            msg = await self.ask_user()
            if msg.content.lower() == 'q':
                await self.message.edit(content="Exiting to main menu....")
                return

            if msg.attachments:
                image = msg.attachments[0].url
            else:
                image = msg.content

            if not await check_url_image(image):
                await self.message.edit(content="Invalid image given, please try again (`q` to quit)")
                continue

            break

        self.custom_embed.set_image(url=image)
        await self.message.edit(content="Success!")

    @menus.button("\N{FOOTPRINTS}")
    async def set_footer(self, payload):
        """Set's the embed's footer"""
        footer_data = {}
        progress_embed = discord.Embed(title="Footer wizard progress", color=discord.Color.blurple())
        await self.message.edit(content="Set the footer's text (`q` to quit)")
        while True:
            msg = await self.ask_user()
            text = msg.content
            if not text:
                await self.message.edit(content="No text was provided, please try again!")
                continue
            elif text.lower() == "q":
                await self.message.edit(content="Exiting to main menu....")
                return

            break

        footer_data.update({'text': text})
        progress_embed.add_field(name="Text", value=f"`{text}`", inline=False)

        await self.message.edit(
            content="Upload a picture post a link to a picture to set as the embed's image. (`skip` to skip, `q` to quit)")
        while True:
            msg = await self.ask_user()
            if msg.content.lower() == 'skip':
                await self.message.edit(content="Skipping....")
                break
            elif msg.content.lower() == 'q':
                await self.message.edit(content="Exiting to main menu....")
                return

            if msg.attachments:
                icon = msg.attachments[0].url
            else:
                icon = msg.content

            if not await check_url_image(icon):
                await self.message.edit(content="Invalid url, please send an image. (`skip` to skip, `q` to quit)")
                continue

            footer_data.update({"icon_url": icon})
            progress_embed.add_field(name="Icon", value=icon, inline=False)
            progress_embed.set_thumbnail(url=icon)
            break

        self.custom_embed.set_footer(**footer_data)
        await self.message.edit(content="Success!")

    @menus.button("\N{MEMO}")
    async def add_field(self, payload):
        """Adds a field to the embed"""
        if len(self.custom_embed.fields) > 10:
            return await self.message.edit(content="You have 10 embed fields, you cannot add any more!")
        field_data = {}
        progress_embed = discord.Embed(title="Field Wizard Progress", color=discord.Color.blurple())
        await self.message.edit(content="What would you like to title this field (`q` to quit)")
        while True:
            msg = await self.ask_user()
            if not msg.content:
                await self.message.edit(content="Please enter message content.")
                continue

            elif len(msg.content) > 256:
                await self.message.edit(content="Name is too long, try again!")
                continue

            elif msg.content.lower() == 'q':
                await self.message.edit(content="Exiting to main menu.....")
                return

            progress_embed.add_field(name="Name", value=f"`{msg.content}`", inline=False)
            field_data.update({"name": msg.content})
            break

        await self.message.edit(content="Fill in the value of this field (`q` to quit)")
        while True:
            msg = await self.ask_user()
            if not msg.content:
                await self.message.edit(content="Please enter message content.")
                continue

            elif msg.content.lower() == 'q':
                await self.message.edit(content="Exiting to main menu.....")
                return

            progress_embed.add_field(name="Value", value=f"`{msg.content}`", inline=False)
            field_data.update({"value": msg.content})
            break

        await self.message.edit(content="Would you like to have this field be inline? (yes/no)")
        msg = await self.ask_user()
        if re.match(r"n[o]*", msg.content, re.I):
            progress_embed.add_field(name="Inline", value="NO", inline=False)
            field_data.update({'inline': False})

        else:
            progress_embed.add_field(name="Inline", value="YES", inline=False)
            field_data.update({"inline": True})

        self.custom_embed.add_field(**field_data)
        await self.message.edit(content="Success!")

    @menus.button("\N{FACE WITH NO GOOD GESTURE}")
    async def delete_field(self, payload):
        """Removes a field"""
        if not self.custom_embed.fields:
            return await self.message.edit(
                content="You do not have any embed fields currently that you can delete, use the :pencil: emoji to make some.")

        embed_dict = self.custom_embed.to_dict()
        fields = embed_dict['fields']
        progress_embed = discord.Embed(title="Current fields.", color=discord.Color.blurple())
        for num, field in enumerate(fields, start=1):
            progress_embed.add_field(name=f"{num}:", value=field['name'])

        await self.message.edit(content="What field number do you want to delete? (`q` to quit)", embed=progress_embed)
        while True:
            msg = await self.ask_user()
            index = None
            if msg.content.lower() == 'q':
                return await self.message.edit(content="Exiting to menu....")
            try:
                index = int(msg.content)
            except ValueError:
                await self.message.edit(content="You need to enter a number")
                continue

            if not index in range(len(embed_dict['fields']) + 1):
                await self.message.edit(content="Invalid index, try again")
                continue

            self.custom_embed.remove_field(index - 1)
            await self.message.edit(content="Success!")
            break

    @menus.button("\N{BLACK RIGHT-POINTING TRIANGLE WITH DOUBLE VERTICAL BAR}")
    async def show_embed(self, payload):
        """Previews the embed"""
        if self.custom_embed is not None:
            await self.message.edit(content="Here is a preview of your embed", embed=self.custom_embed)
        else:
            await self.message.edit(embed=discord.Embed(title="Uh oh! you haven't start making your custom embed.",
                                                        description="Use the buttons below to start making your embed. Use the :question:",
                                                        color=discord.Color.red()))


def setup(bot):
    bot.add_cog(CustomCommands(bot))
