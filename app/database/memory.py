import aiosqlite


DATABASE_PATH = "atlas.db"


async def initialize_database():
    async with aiosqlite.connect(DATABASE_PATH) as db:

        await db.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_user_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                message TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_user_id INTEGER NOT NULL,
                memory_key TEXT NOT NULL,
                memory_value TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(telegram_user_id, memory_key)
            )
        """)

        await db.commit()


async def save_message(
    telegram_user_id: int,
    role: str,
    message: str
):
    async with aiosqlite.connect(DATABASE_PATH) as db:

        await db.execute(
            """
            INSERT INTO conversations
            (telegram_user_id, role, message)
            VALUES (?, ?, ?)
            """,
            (
                telegram_user_id,
                role,
                message
            )
        )

        await db.commit()


async def save_user_memory(
    telegram_user_id: int,
    memory_key: str,
    memory_value: str
):
    import json

    async with aiosqlite.connect(DATABASE_PATH) as db:

        # Ensure lists/dicts are stored as JSON strings
        to_store = memory_value
        if isinstance(memory_value, (list, dict)):
            to_store = json.dumps(memory_value)

        await db.execute(
            """
            INSERT INTO user_memory
            (telegram_user_id, memory_key, memory_value)
            VALUES (?, ?, ?)
            ON CONFLICT(telegram_user_id, memory_key) DO UPDATE SET
            memory_value = excluded.memory_value,
            updated_at = CURRENT_TIMESTAMP
            """,
            (
                telegram_user_id,
                memory_key,
                to_store,
            )
        )

        await db.commit()


async def get_user_memory(
    telegram_user_id: int
):
    async with aiosqlite.connect(DATABASE_PATH) as db:

        cursor = await db.execute(
            """
            SELECT memory_key, memory_value
            FROM user_memory
            WHERE telegram_user_id = ?
            ORDER BY id ASC
            """,
            (
                telegram_user_id,
            )
        )

        rows = await cursor.fetchall()

    # return as dict, parsing JSON values when appropriate
    import json

    result = {}
    for k, v in rows:
        if not v:
            result[k] = v
            continue

        try:
            parsed = json.loads(v)
            result[k] = parsed
        except Exception:
            # not JSON, return raw string
            result[k] = v

    return result


async def get_recent_messages(
    telegram_user_id: int,
    limit: int = 12
):
    async with aiosqlite.connect(DATABASE_PATH) as db:

        cursor = await db.execute(
            """
            SELECT role, message
            FROM conversations
            WHERE telegram_user_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (
                telegram_user_id,
                limit
            )
        )

        rows = await cursor.fetchall()

    rows.reverse()

    return rows


async def get_all_users() -> list[int]:
    """Get all unique user IDs that have interacted with the bot."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute("SELECT DISTINCT telegram_user_id FROM user_memory")
        rows = await cursor.fetchall()
        
    return [row[0] for row in rows]