from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest

from config import EXEMPT_USER_IDS, REQUIRED_CHANNELS

SUBSCRIBED_STATUSES = {"member", "administrator", "creator"}


async def is_subscribed(bot: Bot, username: str, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=f"@{username}", user_id=user_id)
        return member.status in SUBSCRIBED_STATUSES
    except TelegramBadRequest:
        return False


async def get_missing_channels(
    bot: Bot, user_id: int, channels: list[dict] | None = None
) -> list[dict]:
    """Return the channels (from `channels`, default: the 2 required channels) the user hasn't joined.
    Exempt users never miss any channel."""
    if user_id in EXEMPT_USER_IDS:
        return []
    if channels is None:
        channels = REQUIRED_CHANNELS
    missing = []
    for channel in channels:
        if not await is_subscribed(bot, channel["username"], user_id):
            missing.append(channel)
    return missing
