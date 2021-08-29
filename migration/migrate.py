# script to migrate terrygon's old schema to the new schema 
# TODO: make dynamic
# its async cause i dont wanna learn a new lib lol

import asyncio
import os
import typing
import argparse
import asyncpg
from typing import List, Dict
import json


async def set_json_codec(db_connection: asyncpg.Connection):
    """Sets codec connection"""
    await db_connection.set_type_codec('jsonb', encoder=json.dumps, decoder=json.loads, schema='pg_catalog')


async def get_data(db_connection: asyncpg.Connection, schema: str) -> Dict[str, List[dict]]:
    """Gets an entire schema's db data"""
    tables = await db_connection.fetch("SELECT table_name FROM information_schema.tables WHERE table_schema = $1",
                                       schema)
    out = {}
    for table in tables:
        table = table['table_name']
        out[table] = await db_connection.fetch(f"SELECT * FROM {schema}.{table}")
    return out


async def json_to_table(json_data: dict, mappings: dict):
    """Makes a json column its own table"""
    if not mappings:
        raise KeyError("No json data given.")
    new_data = []
    for key, inner in json_data.items():
        if key.isnumeric():
            key = int(key)
        new_entry = {mappings['json_key']: key}
        inner = json.loads(inner)
        for j_name, item in inner.items():
            if not mappings.get(j_name):
                continue

            new_entry[mappings[j_name]] = item

        new_data.append(new_entry)

    return new_data


async def insert_new_data(new_data: list, new_table_name: str, new_db: asyncpg.Connection, old_table: list = None,
                          **kwargs):
    for data in new_data:
        place_holders = [f"${n}" for n in range(1, len(data.values()) + 1)]
        query = f"INSERT INTO {new_table_name} ({', '.join(data.keys())}) VALUES ({', '.join(place_holders)})"
        args = list(data.values())
        try:
            for i in range(0, len(args)):
                if isinstance(args[i], dict):
                    args[i] = json.dumps(args[i])
            await new_db.execute(query, *args)
        except asyncpg.UniqueViolationError:
            pass

        # cross table transferring
    if kwargs.get('cross_table'):
        cross_data = []
        for data in old_table:
            new_entry = {}
            for key, value in data.items():
                if key == 'guildid':
                    new_entry['guild_id'] = value
                if value and key in kwargs['cross_table_maps'].keys():
                    new_entry[kwargs['cross_table_maps'][key]] = value
                    cross_data.append(new_entry)

        for data in cross_data:
            place_holders = [f"${n}" for n in range(1, len(data.values()) + 1)]
            query = f"INSERT INTO {kwargs['cross_table']} ({', '.join(data.keys())}) VALUES ({', '.join(place_holders)})"
            args = data.values()
            try:
                await new_db.execute(query, *args)
            except asyncpg.UniqueViolationError:
                find_unique_query = """SELECT a.attname, format_type(a.atttypid, a.atttypmod) AS data_type
                               FROM   pg_index i JOIN   pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey) 
                               WHERE i.indrelid = $1::regclass AND i.indisunique;"""
                c = await new_db.execute(find_unique_query, kwargs['cross_table'])
                key = await new_db.execute(f"SELECT {c} FROM {kwargs['cross_table']}")
                await new_db.execute(f"DELETE FROM {kwargs['cross_table']} WHERE {c} = $1", key)
                await new_db.execute(query, *args)

    print(f"Transferred to {new_table_name}")


async def transfer_json_row_to_table(old_row: dict, column_mapping: dict, json_maps: dict):
    new_entry = {}
    new_data = []
    non_json_data = {}
    json_data = None
    for key, value in old_row.items():
        if not column_mapping.get(key):
            continue
        if column_mapping[key] == 'json_data':
            json_data = await json_to_table(value, json_maps)
        else:
            non_json_data[column_mapping[key]] = value

    for d in json_data:
        h = new_entry.copy()
        n = non_json_data.copy()
        h.update(**n)
        h.update(**d)
        new_data.append(h)

    return new_data


async def transfer_data(old_data: typing.Union[list, dict], new_table_name: str, new_db: asyncpg.Connection,
                        column_mapping: dict,
                        **kwargs):
    """
    Transfers data over
    Keys - Old columns
    Values - New columns
    """
    new_data = []
    if kwargs.get("is_memes"):
        new_data = await handle_memes(old_data)

    else:
        if kwargs.get('json_maps'):
            new_data = await transfer_json_row_to_table(old_data, column_mapping, json_maps=kwargs['json_maps'])
            await insert_new_data(new_data, new_table_name, new_db, old_data)
            return
        for row in old_data:
            new_entry = {}
            for key, value in row.items():
                if not column_mapping.get(key):
                    continue

                new_entry[column_mapping[key]] = value
            new_data.append(new_entry)
    await insert_new_data(new_data, new_table_name, new_db, old_data, **kwargs)


async def handle_memes(meme_data: list) -> list:
    """Transport memes"""
    new_data = []
    for data in meme_data:
        if data['guildmemes'] is None:
            continue
        new_entry = {'guild_id': data['guildid']}
        for name, content in data['guildmemes'].items():
            new_entry['name'] = name
            new_entry['content'] = content
            new_data.append(new_entry.copy())

    return new_data


# driving code
async def main(old_db_path: str, new_db_path: str):
    """Transfers old data db sequence"""
    # TODO: argparser
    old_db = await asyncpg.connect(old_db_path)
    await set_json_codec(old_db)
    print("Connecting to old db")
    old_data = await get_data(old_db, 'public')
    print("Fetched data.")
    new_db = await asyncpg.connect(new_db_path, server_settings={'search_path': "terrygon"})
    print("Connected to new db.")

    # guild settings
    await transfer_data(old_data['guild_settings'], 'guild_settings', new_db, dict({
        'guildid': 'guild_id',
        'approvalsystem': 'approval_system',
        'enablejoinleavelogs': 'enable_join_leave_logs',
        'enablecoremessageLogs': 'enable_core_message_logs',
        'warn_punishments': 'warn_punishments',
        'staff_filter': 'staff_filter',
        'warn_automute_time': 'warn_automute_time',
        'prefixes': 'prefixes'

    }), keep_json=True)

    log_channels_guild_id = [x['guildid'] for x in old_data['log_channels']]
    new_log_channels = []
    tmp = {}
    for i in old_data['guild_settings']:
        if i['guildid'] in log_channels_guild_id and i['approvalchannel']:
            tmp[i['guildid']] = i['approvalchannel']

    for g_id, channel in tmp.items():
        for entry in old_data['log_channels']:
            new_entry = dict(entry).copy()
            if entry['guildid'] == g_id:
                new_entry["approvalchannel"] = channel
            else:
                new_entry['approvalchannel'] = None
            new_log_channels.append(new_entry)

    old_data['log_channels'] = new_log_channels

    # json
    for color_data in old_data['colors']:
        if color_data['communal_role_data']:
            await transfer_data(color_data, 'communal_colors', new_db, dict({
                'guildid': 'guild_id',
                'communal_role_data': 'json_data'
            }), json_maps=dict({
                'json_key': 'keyword',
                'roleid': 'role_id',
                'colorhex': 'color_hex'
            }))

        elif color_data['personal_role_data']:
            await transfer_data(color_data, 'personal_colors', new_db, dict({
                'guildid': 'guild_id',
                'personal_role_data': 'json_data'
            }), json_maps=dict({
                'json_key': 'user_id',
                'roleid': 'role_id',
                'colorhex': 'color_hex'
            }))

        elif color_data.get('colormode'):
            await transfer_data(old_data['colors'], 'color_settings', new_db, dict({
                'guildid': 'guild_id',
                'colormode': 'mode'
            }))

    for toggles_data in old_data['toggleroles']:
        if toggles_data['roles']:
            await transfer_data(toggles_data, 'toggle_roles', new_db, dict({
                'guildid': 'guild_id',
                'roles': 'json_data'
            }), json_maps=dict({
                'json_key': 'keyword',
                'emoji': 'emoji',
                'roleid': 'role_id',
                'description': 'description'
            }))

    # memes
    await transfer_data(old_data['memes'], 'memes', new_db, dict(), is_memes=True)

    # warns
    await transfer_data(old_data['warns'], 'warns', new_db, dict({
        'warnid': 'warn_id',
        'userid': 'user_id',
        'authorid': 'author_id',
        'guildid': 'guild_id',
        'time_stamp': 'time_stamp',
        'reason': 'reason'
    }))

    # roles
    await transfer_data(old_data['roles'], 'roles', new_db, dict({
        'guildid': 'guild_id',
        'modrole': 'mod_role',
        'adminrole': 'admin_role',
        'ownerrole': 'owner_role',
        'approvedrole': 'approved_role',
        'mutedrole': 'muted_role'
    }))

    # mute
    await transfer_data(old_data['mutes'], 'mutes', new_db, dict({
        'id': 'id',
        'userid': 'user_id',
        'authorid': 'author_id',
        'guildid': 'guild_id',
        'reason': 'reason'
    }))

    # bans
    await transfer_data(old_data['bans'], 'bans', new_db, dict({
        'id': 'id',
        'userid': 'user_id',
        'authorid': 'author_id',
        'guildid': 'guild_id',
        'reason': 'reason'
    }))

    # log_channels
    await transfer_data(old_data['log_channels'], 'channels', new_db, dict({
        'guildid': 'guild_id',
        'modlogs': 'mod_logs',
        'messagelogs': 'message_logs',
        'memberlogs': 'member_logs',
        'filterlogs': 'filter_logs',
        'approvalchannel': 'approval_channel'
    }))

    # approved
    await transfer_data(old_data['approvedmembers'], 'approved_members', new_db, dict({
        'userid': 'user_id',
        'guildid': 'guild_id'
    }))

    # trusted
    await transfer_data(old_data['trustedusers'], 'trusted_users', new_db, dict({
        'guildid': 'guild_id',
        'trusteduid': 'trusted_uid'
    }))

    # channel_block
    await transfer_data(old_data['channel_block'], 'channel_block', new_db, dict({
        'userid': 'user_id',
        'guildid': 'guild_id',
        'blocktype': 'block_type',
        'channelid': 'channel_id',
        'reason': 'reason'
    }))

    print("Finished.")

if os.name == 'nt':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# get args
parser = argparse.ArgumentParser(description="Migrates database for terrygon.")
parser.add_argument('old_path', type=str, help="database path that is being migrated. eg: (postgres://user:pass@domain:port)")
parser.add_argument("new_path", type=str, help="new database that you are migrating to. eg: (postgres://user:pass@domain:port)")

args = parser.parse_args()
asyncio.run(main(args[0], args[1]))
