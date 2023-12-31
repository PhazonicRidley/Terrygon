# Terrygon, a multipurpose discord bot
A modular discord bot written in Python

*Notice: This repo is a rewrite of [this](https://gitlab.com/PhazonicRidley/terrygon) repo. This bot is currently underconstruction*

## Features:
Fully featured bot including but not limited to:
User warning system with optional punishments
Customizable word filter
Moderation commands to handle any situation (if they worked /s)
Approval system to prevent raiding and keep private servers private
Allow some users to have access to more features if they are trusted in a community
Customizable self roles
Colors for either each user or communally used colors depending on how a server wishes to configure
And much much more!

## How to use:

### Manually:
1. Install Python 3.9+ and postgresql 13.
2. Create a postgres user (By default the schema expects a user called `terrygon`. If you plan to use a different name, change the first line in `schema.sql`).
3. Clone the project locally and cd into it.
4. Create a venv `python3 -m venv virtualenv`, and activate it `source virtualenv/bin/activate`.
5. Run `python -m pip install --upgrade pip` and then `python -m pip install -r requirements.txt`.
4. Next, run `cp config.toml.example config.toml` if you are on linux or macos, `copy config.toml.example config.toml` if you are on windows.
6. Edit the `config.toml` fields with your information. Each field is labled on what it does, if you need help making a bot token, you can check [here](https://tinyurl.com/yad4qmz3) for instructions on making it and adding it to your server.
7. Change the paths in `terrygon.service` for where your bot is located, and where the virtualenv is located.
8. Copy `terrygon.service` to `~/.config/systemd/user`.
9. Run commands `systemctl --user daemon-reload` and then finally `systemctl --user start terrygon.service`. You may also choose to enable this at start up.

### Docker:
1. Install Docker and then clone this repository.
2. Enter the cloned repo directory in a terminal.
3. Run `cp config.toml.example config.toml` if you are on linux or macos, `copy config.toml.example config.toml` if you are on windows.
4. Edit the `config.toml` fields with your information. Each field is labled on what it does, if you need help making a bot token, you can check [here](https://tinyurl.com/yad4qmz3) 
5. Run `docker compose up -d` and docker will automatically make a containerized bot. The `data` folder is a volume into the container.

## Requirements
- Python 3.9 or later
- Python modules:
    - [discord.py](https://github.com/Rapptz/discord.py/tree/rewrite)
    - [pylast](https://github.com/pylast/pylast)
    - [qrcode](https://github.com/lincolnloop/python-qrcode)
    - [Pillow](https://github.com/python-pillow/Pillow)
    - [logzero](https://github.com/metachris/logzero)
    - [asyncpg](https://github.com/MagicStack/asyncpg)
    - [pyymal](https://github.com/yaml/pyyaml)
    - [tabulate](https://github.com/astanin/python-tabulate)

- PostgresSQL 13
- Linux machine
- systemd to use the systemd service

## Credits
- [Rapptz](https://github.com/Rapptz) for [discord.py](https://github.com/Rapptz/discord.py/tree/rewrite).
- [astronautlevel](https://github.com/astronautlevel2) for her [QR code addon](https://github.com/astronautlevel2/Discord-Cogs/blob/master/qrgen.py).
- [T3CHNOLOG1C](https://github.com/T3CHNOLOG1C) for the orginal code.
- [Snowfall](https://gitlab.com/lightning-bot/Lightning) for general advice and code inspiration.
- [Noirscape](https://git.catgirlsin.space/noirscape/) for general advice and code inspiration.
- The on my discord server for naming the bot.
- My friends on my discord server and exelix's server who gave me inspiration and a will to work on this.
