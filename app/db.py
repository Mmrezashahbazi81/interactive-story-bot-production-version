from pathlib import Path

import aiosqlite

from app.config import settings


CREATE_TABLES_SQL = [
    """
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        first_name TEXT,
        last_name TEXT,
        username TEXT,
        has_started_private INTEGER NOT NULL DEFAULT 0,
        gender TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS memberships (
        user_id INTEGER NOT NULL,
        channel_id TEXT NOT NULL,
        status TEXT NOT NULL,
        checked_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (user_id, channel_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS stories (
        story_id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        genre TEXT,
        min_players INTEGER NOT NULL DEFAULT 1,
        max_players INTEGER NOT NULL DEFAULT 4,
        metadata_json TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS games (
        game_id TEXT PRIMARY KEY,
        chat_id TEXT NOT NULL,
        chat_type TEXT NOT NULL,
        owner_user_id INTEGER NOT NULL,
        state TEXT NOT NULL,
        story_id TEXT,
        current_node_id TEXT,
        current_turn_user_id INTEGER,
        message_id INTEGER,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS game_players (
        game_id TEXT NOT NULL,
        user_id INTEGER NOT NULL,
        display_name TEXT,
        gender TEXT,
        role_id TEXT,
        turn_order INTEGER,
        is_ready INTEGER NOT NULL DEFAULT 0,
        joined_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (game_id, user_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS game_events (
        event_id INTEGER PRIMARY KEY AUTOINCREMENT,
        game_id TEXT NOT NULL,
        user_id INTEGER,
        event_type TEXT NOT NULL,
        payload_json TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """,
]


def ensure_db_directory() -> None:
    db_path = Path(settings.database_path)
    db_dir = db_path.parent
    if str(db_dir) not in ("", "."):
        db_dir.mkdir(parents=True, exist_ok=True)


async def get_db() -> aiosqlite.Connection:
    ensure_db_directory()
    db = await aiosqlite.connect(settings.database_path)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA foreign_keys=ON;")
    await db.execute("PRAGMA synchronous=NORMAL;")
    await db.execute("PRAGMA temp_store=MEMORY;")
    await db.execute("PRAGMA cache_size=-20000;")
    return db


async def init_db() -> None:
    db = await get_db()
    try:
        for sql in CREATE_TABLES_SQL:
            await db.execute(sql)
        await db.commit()
    finally:
        await db.close()