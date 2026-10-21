"""Save the user list to your Mac, or move it into another database.

Save a copy of the Neon database to a file in this folder:
    python3 backup.py save

Move it into Railway (from a saved file into the database in DATABASE_URL):
    DATABASE_URL="..." python3 backup.py load users-2026-10-21.json
"""
import asyncio
import json
import os
import sys
from datetime import datetime

import asyncpg

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

COLUMNS = [
    "user_id", "first_name", "last_name", "username", "start_count",
    "book_message_ids", "prompt_message_id", "has_received_book", "created_at",
]


def clean_url(url: str) -> str:
    # Neon adds "channel_binding=require", which this library doesn't understand.
    return url.replace("&channel_binding=require", "").replace("channel_binding=require&", "")


async def save(url: str) -> None:
    conn = await asyncpg.connect(clean_url(url))
    rows = await conn.fetch(f"SELECT {', '.join(COLUMNS)} FROM users ORDER BY created_at")
    await conn.close()
    data = []
    for r in rows:
        d = dict(r)
        d["book_message_ids"] = list(d["book_message_ids"] or [])
        d["created_at"] = d["created_at"].isoformat()
        data.append(d)
    name = f"users-{datetime.now():%Y-%m-%d}.json"
    with open(name, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    print(f"Saved {len(data)} users to {name}")


async def load(url: str, path: str) -> None:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    conn = await asyncpg.connect(clean_url(url))
    await conn.execute(CREATE_TABLE_SQL)
    placeholders = ", ".join(f"${i}" for i in range(1, len(COLUMNS) + 1))
    updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in COLUMNS[1:])
    sql = (
        f"INSERT INTO users ({', '.join(COLUMNS)}) VALUES ({placeholders}) "
        f"ON CONFLICT (user_id) DO UPDATE SET {updates}"
    )
    for d in data:
        d["created_at"] = datetime.fromisoformat(d["created_at"])
        await conn.execute(sql, *[d[c] for c in COLUMNS])
    await conn.close()
    print(f"Moved {len(data)} users into the new database")


if __name__ == "__main__":
    db_url = os.environ.get("DATABASE_URL")
    if not db_url and os.path.exists("neon_url.txt"):
        # Saved by setup_render.sh — the Neon database.
        db_url = open("neon_url.txt").read().strip()
    if not db_url or len(sys.argv) < 2 or sys.argv[1] not in {"save", "load"}:
        print(__doc__)
        sys.exit(1)
    if sys.argv[1] == "save":
        asyncio.run(save(db_url))
    else:
        asyncio.run(load(db_url, sys.argv[2]))
