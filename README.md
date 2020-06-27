# Terrygon, a multipurpose  discord bot
A modular discord bot written in Python

**Current Release**: v0.7-BETA

## A quick note
This bot exists because I wanted to get better at programming and try out new territory with programming.
Right now almost everything is a work in progress, I have a to do list on what I plan to do ~~when I don't feel so lazy and get motivation back~~
Also, its 2 am while I write this so probably best to just ignore everything in here except for the part about this being a WIP.

## Features:
- Mostly configurable via configuration file.
- Supports multiple servers
- Uses a full database system
- Support for toggable approval system based servers
- Channel lockdowns (including remote lockdowns)
- Join/Leave logs (Toggleable)
- Kick/Ban/Softban
- Mute/Unmute
- Warning system (3rd/4th warns kick, 5th bans)
- Custom Cog system. (WIP)

## Base Custom Cogs
- Generate QR Codes for attachments or URLs
- Keep track of user's accounts that can be queried at anytime
- toggleable color role system, either communal color roles or personal color roles
- Togglable roles, fully dynamic for each server
- Dynamic meme system per server


*Notice: Linux support only at moment for exit, restart, and pull commands as they use a systemd service. You may use jsk to do some of these actions in the mean time.*

## How to use:
Uh well docker image soonTM. In the mean time:

1. Install Python 3.7+ and postgresql 12.
2. Create a postgres user (By default the schema expects a user called `bot` if you do not use that name,
3. change the first line in schema.sql)
4. Run `python -m pip install --upgrade pip` and then `python -m pip install -r requirements.txt`.
5. Next, run `cp config.yml.example config.yml` if you are on linux or macos, `copy config.yml.example config.yml` if you are on windows.
6. Edit the `config.yml` fields with your information. Each field is labled on what it does, if you need help making a bot token, you can check [here](https://tinyurl.com/yad4qmz3) for instructions on making it and adding it to your server.
7. Change the paths in `terrygon.service` for where your bot files will be.
8. Copy `terrygon.service` to `~/.config/systemd/user`.
9. Run commands `systemd --user daemon-reload` and then finally `systemd --user start terrygon.service`. You may also choose to enable this at start up.

## Requirements
- Python 3.7 or later
- Python modules:
    - [discord.py](https://github.com/Rapptz/discord.py/tree/rewrite)
    - [pylast](https://github.com/pylast/pylast)
    - [qrcode](https://github.com/lincolnloop/python-qrcode)
    - [Pillow](https://github.com/python-pillow/Pillow)
    - [logzero](https://github.com/metachris/logzero)
    - [asyncpg](https://github.com/MagicStack/asyncpg)
    - [pyymal](https://github.com/yaml/pyyaml)
    - [tabulate](https://github.com/astanin/python-tabulate)

- PostgresSQL 12
- Linux machine
- systemd to use the systemd service

## Credits
- [Rapptz](https://github.com/Rapptz) for [discord.py](https://github.com/Rapptz/discord.py/tree/rewrite).
- [astronautlevel](https://github.com/astronautlevel2) for her [QR code addon](https://github.com/astronautlevel2/Discord-Cogs/blob/master/qrgen.py).
- [T3CHNOLOG1C](https://github.com/T3CHNOLOG1C) for the orginal code.
- [Snowfall](https://gitlab.com/lightning-bot/Lightning) for general advice and code inspiration.
- [Noirscape](https://git.catgirlsin.space/noirscape/) for general advice and code inspiration.
- The █▀█ █▄█ ▀█▀ discord server for naming the bot
- My friends on █▀█ █▄█ ▀█▀ and exelix's server who gave me inspiration and a will to work on this.
