from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def channels_keyboard(channels: list[dict]) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text=ch["name"], url=f"https://t.me/{ch['username']}")]
        for ch in channels
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)
