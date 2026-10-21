import asyncio
import logging

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

import config
import db
from subscriptions import get_missing_channels

logger = logging.getLogger(__name__)
router = Router()

CATEGORY_ALL = "all"
CATEGORY_MISSING = "missing"
CATEGORY_GOT_BOOK = "got_book"

CATEGORY_LABELS = {
    CATEGORY_ALL: "Barcha foydalanuvchilarga xabar yuborish",
    CATEGORY_MISSING: "Hali kanallarga a'zo bo'lmaganlarga xabar yuborish",
    CATEGORY_GOT_BOOK: "Materiallarni olganlarga xabar yuborish",
}

NO_BROADCAST_IDS = {8143024822, 672690832, 2057867046, 6173729606, 539948403}


class BroadcastState(StatesGroup):
    choosing_category = State()
    waiting_for_message = State()
    confirming = State()


def is_admin(user_id: int) -> bool:
    return user_id in config.ADMIN_TELEGRAM_IDS


def category_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text=label, callback_data=f"bcat:{key}")]
        for key, label in CATEGORY_LABELS.items()
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Yuborish", callback_data="bconfirm:yes"),
                InlineKeyboardButton(text="❌ Bekor qilish", callback_data="bconfirm:no"),
            ]
        ]
    )


@router.message(Command("broadcast"))
async def cmd_broadcast(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        return
    await state.set_state(BroadcastState.choosing_category)
    await message.answer("Qaysi guruhga xabar yubormoqchisiz?", reply_markup=category_keyboard())


@router.callback_query(BroadcastState.choosing_category, F.data.startswith("bcat:"))
async def choose_category(callback: CallbackQuery, state: FSMContext) -> None:
    category = callback.data.split(":", 1)[1]
    await state.update_data(category=category)
    await state.set_state(BroadcastState.waiting_for_message)
    await callback.message.edit_text(
        f"Tanlandi: {CATEGORY_LABELS[category]}\n\n"
        "Endi yubormoqchi bo'lgan xabaringizni yuboring "
        "(matn, rasm, video, fayl — istalgan turda bo'lishi mumkin)."
    )
    await callback.answer()


@router.message(BroadcastState.waiting_for_message)
async def receive_broadcast_message(message: Message, state: FSMContext) -> None:
    await state.update_data(source_chat_id=message.chat.id, source_message_id=message.message_id)
    await state.set_state(BroadcastState.confirming)
    await message.answer(
        "Xabar shu ko'rinishda yuboriladi. Tasdiqlaysizmi?", reply_markup=confirm_keyboard()
    )


@router.callback_query(BroadcastState.confirming, F.data.startswith("bconfirm:"))
async def confirm_broadcast(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    decision = callback.data.split(":", 1)[1]
    data = await state.get_data()
    await state.clear()

    if decision == "no":
        await callback.message.edit_text("Bekor qilindi.")
        await callback.answer()
        return

    await callback.message.edit_text("Yuborilmoqda... Bu biroz vaqt olishi mumkin.")
    await callback.answer()

    category = data["category"]
    source_chat_id = data["source_chat_id"]
    source_message_id = data["source_message_id"]

    user_ids = await get_target_user_ids(bot, category)
    user_ids = [uid for uid in user_ids if uid not in NO_BROADCAST_IDS]

    sent = 0
    failed = 0
    for user_id in user_ids:
        try:
            await bot.copy_message(
                chat_id=user_id, from_chat_id=source_chat_id, message_id=source_message_id
            )
            sent += 1
        except Exception:
            logger.warning("Broadcast failed for %s", user_id, exc_info=True)
            failed += 1
        await asyncio.sleep(0.05)

    await bot.send_message(
        callback.from_user.id,
        f"Yakunlandi. Yuborildi: {sent}, xatolik: {failed}.",
    )


async def get_target_user_ids(bot: Bot, category: str) -> list[int]:
    all_users = await db.get_all_user_ids()

    if category == CATEGORY_ALL:
        return all_users
    if category == CATEGORY_GOT_BOOK:
        return await db.get_user_ids_with_book()

    targets: list[int] = []
    semaphore = asyncio.Semaphore(10)

    async def check(user_id: int) -> None:
        async with semaphore:
            missing = await get_missing_channels(bot, user_id, config.REQUIRED_CHANNELS)
            if missing:
                targets.append(user_id)

    await asyncio.gather(*(check(uid) for uid in all_users))
    return targets
