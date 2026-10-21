from __future__ import annotations

import asyncpg

from config import DATABASE_URL

pool: asyncpg.Pool | None = None

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS users (
    user_id BIGINT PRIMARY KEY,
    first_name TEXT,
    last_name TEXT,
    username TEXT,
    start_count INTEGER NOT NULL DEFAULT 0,
    book_message_ids BIGINT[] NOT NULL DEFAULT '{}',
    prompt_message_id BIGINT,
    has_received_book BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


async def init_pool() -> None:
    global pool
    pool = await asyncpg.create_pool(DATABASE_URL)
    async with pool.acquire() as conn:
        await conn.execute(CREATE_TABLE_SQL)


async def close_pool() -> None:
    if pool is not None:
        await pool.close()


async def record_start(
    user_id: int,
    first_name: str | None,
    last_name: str | None,
    username: str | None,
) -> bool:
    """Insert or update a user on /start. Returns True if this was their first ever start."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO users (user_id, first_name, last_name, username, start_count)
            VALUES ($1, $2, $3, $4, 1)
            ON CONFLICT (user_id) DO UPDATE
            SET start_count = users.start_count + 1,
                first_name = EXCLUDED.first_name,
                last_name = EXCLUDED.last_name,
                username = EXCLUDED.username
            RETURNING (xmax = 0) AS is_first_time
            """,
            user_id,
            first_name,
            last_name,
            username,
        )
        return bool(row["is_first_time"])


async def delete_user(user_id: int) -> bool:
    """Admin reset: remove the user completely, so their next /start counts as new.
    Returns True if the user existed."""
    async with pool.acquire() as conn:
        result = await conn.execute("DELETE FROM users WHERE user_id = $1", user_id)
        return result.endswith(" 1")


async def user_exists(user_id: int) -> bool:
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT 1 FROM users WHERE user_id = $1", user_id)
        return row is not None


async def mark_materials_sent(user_id: int, message_ids: list[int]) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET book_message_ids = $1, has_received_book = TRUE WHERE user_id = $2",
            message_ids,
            user_id,
        )


async def set_material_message_ids(user_id: int, message_ids: list[int]) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET book_message_ids = $1 WHERE user_id = $2",
            message_ids,
            user_id,
        )


async def get_material_message_ids(user_id: int) -> list[int]:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT book_message_ids FROM users WHERE user_id = $1", user_id
        )
        return list(row["book_message_ids"] or []) if row else []


async def set_prompt_message_id(user_id: int, message_id: int | None) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET prompt_message_id = $1 WHERE user_id = $2",
            message_id,
            user_id,
        )


async def get_prompt_message_id(user_id: int) -> int | None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT prompt_message_id FROM users WHERE user_id = $1", user_id
        )
        return row["prompt_message_id"] if row else None


async def get_all_user_ids() -> list[int]:
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT user_id FROM users")
        return [r["user_id"] for r in rows]


async def get_user_ids_with_book() -> list[int]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT user_id FROM users WHERE has_received_book = TRUE"
        )
        return [r["user_id"] for r in rows]


async def get_stats() -> dict:
    """Numbers for the top of the admin panel (days in Tashkent time)."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE has_received_book) AS got_materials,
                COUNT(*) FILTER (
                    WHERE (created_at AT TIME ZONE 'Asia/Tashkent')::date
                        = (now() AT TIME ZONE 'Asia/Tashkent')::date
                ) AS today_new,
                COALESCE(SUM(start_count), 0) AS total_starts
            FROM users
            """
        )
        return dict(row)


async def get_total_user_count() -> int:
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT COUNT(*) AS count FROM users")
        return row["count"]


async def fetch_users_page(offset: int, limit: int) -> list[dict]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT user_id, first_name, last_name, username, start_count,
                   has_received_book, created_at
            FROM users
            ORDER BY created_at DESC
            OFFSET $1
            LIMIT $2
            """,
            offset,
            limit,
        )
        return [dict(r) for r in rows]
