import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandStart
from aiogram.types import ChatMemberUpdated, Message

import broadcast
import config
import db
from keyboards import channels_keyboard
from subscriptions import SUBSCRIBED_STATUSES, get_missing_channels

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(
    token=config.BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)
dp = Dispatcher()
dp.include_router(broadcast.router)

WELCOME_TEXT = (
    "<b>Barchasi BEPUL, materiallarni olish uchun quyidagi kanallarga a'zo bo'ling👇</b>\n\n"
    "A'zo bo'lgach, materiallar avtomatik yuboriladi."
)

LEFT_WARNING_TEXT = (
    "❗️Siz kanallardan biridan chiqib ketdingiz, materiallarni olish uchun quyidagi "
    "kanalga a'zo bo'ling👇"
)


async def clear_prompt_message(user_id: int) -> None:
    prompt_message_id = await db.get_prompt_message_id(user_id)
    if prompt_message_id:
        try:
            await bot.delete_message(chat_id=user_id, message_id=prompt_message_id)
        except TelegramBadRequest:
            logger.warning("Could not delete prompt message for %s", user_id)
        await db.set_prompt_message_id(user_id, None)


async def remove_materials(user_id: int) -> None:
    for message_id in await db.get_material_message_ids(user_id):
        try:
            await bot.delete_message(chat_id=user_id, message_id=message_id)
        except TelegramBadRequest:
            logger.warning("Could not delete material message for %s", user_id)
    await db.set_material_message_ids(user_id, [])


async def send_materials(user_id: int) -> None:
    await clear_prompt_message(user_id)
    # Don't send a second set if the user already has them in the chat.
    if await db.get_material_message_ids(user_id):
        await remove_materials(user_id)
    sent_ids: list[int] = []
    for source_message_id in config.SOURCE_MESSAGE_IDS:
        try:
            # copy_message keeps the original caption; protect_content blocks
            # forwarding and saving.
            sent = await bot.copy_message(
                chat_id=user_id,
                from_chat_id=config.SOURCE_CHAT_ID,
                message_id=source_message_id,
                protect_content=True,
            )
            sent_ids.append(sent.message_id)
        except TelegramBadRequest:
            logger.exception(
                "Failed to send material %s to %s", source_message_id, user_id
            )
    if sent_ids:
        await db.mark_materials_sent(user_id, sent_ids)


@dp.message(CommandStart())
async def handle_start(message: Message) -> None:
    user_id = message.from_user.id

    first_time = await db.record_start(
        user_id,
        message.from_user.first_name,
        message.from_user.last_name,
        message.from_user.username,
    )

    channels = config.REQUIRED_CHANNELS
    missing = await get_missing_channels(bot, user_id, channels)

    await clear_prompt_message(user_id)

    if missing:
        # Not allowed to keep the materials while a required channel is missing.
        await remove_materials(user_id)
        shown = channels if first_time else missing
        sent = await message.answer(WELCOME_TEXT, reply_markup=channels_keyboard(shown))
        await db.set_prompt_message_id(user_id, sent.message_id)
        return

    if first_time:
        # Already joined everything: still show both channels (this message
        # stays), then send the materials right under it.
        await message.answer(WELCOME_TEXT, reply_markup=channels_keyboard(channels))
    await send_materials(user_id)


@dp.chat_member()
async def handle_chat_member_update(event: ChatMemberUpdated) -> None:
    chat_username = (event.chat.username or "").lower()
    if chat_username not in config.ALL_CHANNEL_USERNAMES:
        return

    user_id = event.new_chat_member.user.id

    if not await db.user_exists(user_id):
        return

    channels = config.REQUIRED_CHANNELS
    old_status = event.old_chat_member.status
    new_status = event.new_chat_member.status
    was_subscribed = old_status in SUBSCRIBED_STATUSES
    is_now_subscribed = new_status in SUBSCRIBED_STATUSES

    if was_subscribed and not is_now_subscribed:
        await remove_materials(user_id)
        await clear_prompt_message(user_id)

        missing = await get_missing_channels(bot, user_id, channels)
        try:
            sent = await bot.send_message(
                chat_id=user_id,
                text=LEFT_WARNING_TEXT,
                reply_markup=channels_keyboard(missing),
            )
            await db.set_prompt_message_id(user_id, sent.message_id)
        except TelegramBadRequest:
            logger.warning("Could not message user %s after they left a channel", user_id)

    elif not was_subscribed and is_now_subscribed:
        missing = await get_missing_channels(bot, user_id, channels)
        if not missing:
            await send_materials(user_id)


async def main() -> None:
    await db.init_pool()
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await db.close_pool()


if __name__ == "__main__":
    asyncio.run(main())
