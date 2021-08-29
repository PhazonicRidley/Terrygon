CREATE SCHEMA IF NOT EXISTS terrygon;

 -- guild settings
    CREATE TABLE IF NOT EXISTS terrygon.guild_settings
    (
        guild_id BIGINT PRIMARY KEY,
        approval_system BOOLEAN DEFAULT FALSE,
        enable_join_leave_logs BOOLEAN DEFAULT TRUE,
        enable_core_message_logs BOOLEAN DEFAULT TRUE,
        warn_punishments jsonb,
        staff_filter BOOLEAN DEFAULT TRUE,
        auto_probate BOOLEAN DEFAULT FALSE,
        warn_automute_time INT DEFAULT 86400,
        prefixes TEXT[]

    );

    -- log channels
    CREATE TABLE IF NOT EXISTS terrygon.channels
    (
        guild_id BIGINT PRIMARY KEY,
        mod_logs BIGINT,
        member_logs BIGINT,
        message_logs BIGINT,
        filter_logs BIGINT,
        probation_channel BIGINT,
        approval_channel BIGINT
    );

    -- warns
    CREATE TABLE IF NOT EXISTS terrygon.warns
    (
        warn_id SERIAL PRIMARY KEY,
        user_id BIGINT NOT NULL,
        author_id BIGINT NOT NULL,
        guild_id BIGINT NOT NULL,
        time_stamp TIMESTAMP DEFAULT NOW(),
        reason TEXT
    );

    -- roles
    CREATE TABLE IF NOT EXISTS terrygon.roles
    (
        guild_id BIGINT NOT NULL,
        mod_role BIGINT,
        admin_role BIGINT,
        owner_role BIGINT,
        approved_role BIGINT,
        muted_role BIGINT,
        probation_role BIGINT
    );

    -- mute
    CREATE TABLE IF NOT EXISTS terrygon.mutes
    (
        id SERIAL PRIMARY KEY,
        user_id BIGINT NOT NULL,
        author_id BIGINT NOT NULL,
        guild_id BIGINT NOT NULL,
        reason TEXT
    );

    CREATE TABLE IF NOT EXISTS terrygon.probations
    (
        id SERIAL PRIMARY KEY,
        user_id BIGINT NOT NULL,
        author_id BIGINT NOT NULL,
        guild_id BIGINT NOT NULL,
        roles BIGINT[],
        reason TEXT
    );

    -- approval system
    CREATE TABLE IF NOT EXISTS terrygon.approved_members
    (
        user_id BIGINT NOT NULL,
        guild_id BIGINT NOT NULL
    );

    -- ban
    CREATE TABLE IF NOT EXISTS terrygon.bans
    (
        id SERIAL PRIMARY KEY,
        user_id BIGINT NOT NULL,
        author_id BIGINT NOT NULL,
        guild_id BIGINT NOT NULL,
        reason TEXT
    );

    -- memes 
    CREATE TABLE IF NOT EXISTS terrygon.memes (
        guild_id BIGINT, -- 0 = global meme, only exception to not being in guild settings table.
        name TEXT NOT NULL,
        content TEXT NOT NULL -- link or phrase that is to be saved, not saving images directly, not worth it
    );

    -- toggleroles 
    CREATE TABLE IF NOT EXISTS terrygon.toggle_roles
    (
        guild_id BIGINT,
        emoji TEXT,
        keyword TEXT NOT NULL,
        role_id BIGINT NOT NULL,
        description TEXT
    );

    -- colors
    CREATE TABLE IF NOT EXISTS terrygon.color_settings
    (
      guild_id BIGINT PRIMARY KEY,
      mode VARCHAR(9) DEFAULT 'disabled'
    );

    CREATE TABLE IF NOT EXISTS terrygon.communal_colors
    (
      guild_id BIGINT,
      color_hex VARCHAR(7) NOT NULL,
      keyword TEXT NOT NULL,
      role_id BIGINT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS terrygon.personal_colors
    (
      guild_id BIGINT,
      color_hex VARCHAR(7) NOT NULL,
      user_id BIGINT NOT NULL,
      role_id BIGINT NOT NULL
    );

    -- accountinfo
    CREATE TABLE IF NOT EXISTS terrygon.account_info
    (
        user_id BIGINT,
        accounts jsonb
    );

     -- trusted users
    CREATE TABLE IF NOT EXISTS terrygon.trusted_users
    (
        guild_id BIGINT NOT NULL,
        trusted_uid BIGINT[]
    );

    CREATE TABLE IF NOT EXISTS terrygon.channel_block
    (
        id SERIAL PRIMARY KEY,
        user_id BIGINT NOT NULL,
        guild_id BIGINT NOT NULL,
        block_type TEXT[] NOT NULL,
        channel_id BIGINT NOT NULL,
        reason TEXT
    );

    CREATE TABLE IF NOT EXISTS terrygon.timed_jobs
    (
        id SERIAL,
        type TEXT NOT NULL,
        expiration TIMESTAMP NOT NULL,
        extra jsonb
    );

    CREATE TABLE IF NOT EXISTS filtered_words (
        id SERIAL PRIMARY KEY,
        word TEXT,
        guild_id BIGINT,
        punishment TEXT
    );

    CREATE TABLE IF NOT EXISTS whitelisted_channels (
        channel_id BIGINT PRIMARY KEY,
        guild_id BIGINT
    );

    CREATE TABLE IF NOT EXISTS whitelisted_roles (
        role_id BIGINT PRIMARY KEY,
        guild_id BIGINT
    );

    CREATE TABLE IF NOT EXISTS memes (
        guild_id BIGINT PRIMARY KEY,
        name TEXT NOT NULL,
        content TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS accounts (
        user_id BIGINT NOT NULL,
        name TEXT NOT NULL,
        content TEXT NOT NULL
    );

    -- indexes
    CREATE INDEX IF NOT EXISTS warns_idx ON warns (user_id, author_id);
    CREATE INDEX IF NOT EXISTS mutes_idx ON mutes (user_id, author_id);
    CREATE INDEX IF NOT EXISTS role_idx ON roles (guild_id);
    CREATE INDEX IF NOT EXISTS guild_settings_idx ON guild_settings (guild_id);
    CREATE INDEX IF NOT EXISTS approved_idx ON approved_members (user_id);
    CREATE INDEX IF NOT EXISTS bans_idx ON bans (user_id);
    CREATE INDEX IF NOT EXISTS probations_idx ON probations (user_id, author_id);
    CREATE INDEX IF NOT EXISTS accounts_idx ON accounts (user_id);

