import asyncio
import secrets
from urllib.parse import parse_qs, quote

from aiogram import Bot
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

import config
import db
from subscriptions import get_missing_channels

app = FastAPI()
templates = Jinja2Templates(directory="templates")
security = HTTPBasic()

bot = Bot(token=config.BOT_TOKEN)

CONCURRENCY = 10
PAGE_SIZE = 100


def check_auth(credentials: HTTPBasicCredentials = Depends(security)) -> None:
    correct_username = secrets.compare_digest(credentials.username, config.ADMIN_USERNAME)
    correct_password = secrets.compare_digest(credentials.password, config.ADMIN_PASSWORD)
    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )


@app.on_event("startup")
async def startup() -> None:
    await db.init_pool()


@app.on_event("shutdown")
async def shutdown() -> None:
    await db.close_pool()
    await bot.session.close()


async def annotate_missing(users: list[dict]) -> list[dict]:
    semaphore = asyncio.Semaphore(CONCURRENCY)

    async def check(u: dict) -> None:
        async with semaphore:
            missing = await get_missing_channels(bot, u["user_id"], config.REQUIRED_CHANNELS)
            u["missing_names"] = [c["name"] for c in missing]

    await asyncio.gather(*(check(u) for u in users))
    return users


@app.get("/", response_class=HTMLResponse)
async def dashboard(
    request: Request, page: int = 1, msg: str = "", _: None = Depends(check_auth)
) -> HTMLResponse:
    page = max(page, 1)
    offset = (page - 1) * PAGE_SIZE

    stats = await db.get_stats()
    total = stats["total"]
    users = await db.fetch_users_page(offset, PAGE_SIZE)
    users = await annotate_missing(users)

    total_pages = max((total + PAGE_SIZE - 1) // PAGE_SIZE, 1)

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "users": users,
            "total": total,
            "stats": stats,
            "page": page,
            "total_pages": total_pages,
            "has_prev": page > 1,
            "has_next": page < total_pages,
            "msg": msg,
        },
    )


@app.post("/reset")
async def reset_user(request: Request, _: None = Depends(check_auth)) -> RedirectResponse:
    """Delete one user so the bot treats them as brand new on their next /start."""
    form = parse_qs((await request.body()).decode())
    raw_id = (form.get("user_id", [""])[0]).strip()
    page = (form.get("page", ["1"])[0]).strip() or "1"

    if not raw_id.lstrip("-").isdigit():
        msg = "❗️ Telegram ID faqat raqamlardan iborat bo'lishi kerak."
    elif await db.delete_user(int(raw_id)):
        msg = f"✅ {raw_id} reset qilindi — keyingi /start'da yangi foydalanuvchi bo'ladi."
    else:
        msg = f"❗️ {raw_id} ID'li foydalanuvchi topilmadi."

    return RedirectResponse(f"/?page={quote(page)}&msg={quote(msg)}", status_code=303)
