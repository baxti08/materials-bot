"""Render version: the admin panel AND the bot run together in one program
(Render's free plan covers one service). Railway still uses start.sh.

Start command on Render:
    uvicorn render_app:app --host 0.0.0.0 --port $PORT
"""
import asyncio
import contextlib
import logging
import os

import aiohttp

import bot as tg
from admin_panel import app  # its startup opens the database first

logger = logging.getLogger(__name__)

# Render's free plan sleeps after 15 minutes with no visitors, so the app
# visits its own public /ping link every 10 minutes. Render sets this variable.
SELF_URL = os.environ.get("RENDER_EXTERNAL_URL", "")


@app.get("/ping")
async def ping() -> dict:
    return {"ok": True}


async def keep_awake() -> None:
    if not SELF_URL:
        return
    async with aiohttp.ClientSession() as session:
        while True:
            await asyncio.sleep(600)
            try:
                async with session.get(f"{SELF_URL}/ping", timeout=30) as r:
                    await r.read()
            except Exception:
                logger.warning("Keep-awake ping failed", exc_info=True)


@app.on_event("startup")
async def start_bot() -> None:
    app.state.tasks = [
        asyncio.create_task(
            tg.dp.start_polling(
                tg.bot,
                allowed_updates=tg.dp.resolve_used_update_types(),
                handle_signals=False,
            )
        ),
        asyncio.create_task(keep_awake()),
    ]


@app.on_event("shutdown")
async def stop_bot() -> None:
    for task in getattr(app.state, "tasks", []):
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
