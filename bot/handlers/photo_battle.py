"""
FSM-хендлер «Сравнение 2 фото» (Этап D).

Состояния:
- photo_battle_first — ждём первое фото.
- photo_battle_second — ждём второе фото.

Запускается из vibe_hooks.cb_hook_compare (callback hook_compare).
"""

import io

from aiogram import F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from services.analytics.tracker import track
from utils.logging import get_logger

router = Router()
logger = get_logger(__name__)


# ============================================================
# УТИЛИТА: скачать фото
# ============================================================
async def _download_photo(message: Message) -> bytes:
    photo = message.photo[-1]
    file = await message.bot.get_file(photo.file_id)
    buf = io.BytesIO()
    await message.bot.download_file(file.file_path, buf)
    return buf.getvalue()


# ============================================================
# ШАГ 1: ПЕРВОЕ ФОТО
# ============================================================
@router.message(F.photo, StateFilter("photo_battle_first"))
async def handle_first_photo(message: Message, state: FSMContext):
    try:
        image_1 = await _download_photo(message)
    except Exception:
        logger.exception("[BATTLE] first photo download failed")
        await message.answer("😔 Не удалось скачать фото. Попробуй ещё раз.")
        return

    await state.update_data(image_1=image_1)
    await state.set_state("photo_battle_second")

    await message.answer(
        "✅ Первое фото принято.\n\n"
        "Теперь отправь <b>второе фото</b>."
    )


# ============================================================
# ШАГ 2: ВТОРОЕ ФОТО → AI
# ============================================================
@router.message(F.photo, StateFilter("photo_battle_second"))
async def handle_second_photo(message: Message, state: FSMContext):
    data = await state.get_data()
    image_1 = data.get("image_1")
    user_id = data.get("user_id")

    if not image_1 or not user_id:
        await state.clear()
        await message.answer("❌ Что-то пошло не так. Начни заново.")
        return

    await message.answer("⚔️ Устраиваю битву вайбов...")

    try:
        image_2 = await _download_photo(message)
    except Exception:
        logger.exception("[BATTLE] second photo download failed")
        await message.answer("😔 Не удалось скачать фото. Попробуй ещё раз.")
        await state.clear()
        return

    await state.clear()

    try:
        from services.analysis.photo_battle import (
            generate_photo_battle_for_user,
            format_photo_battle,
        )
        result = await generate_photo_battle_for_user(
            user_id=user_id,
            telegram_id=message.from_user.id,
            image_1_bytes=image_1,
            image_2_bytes=image_2,
        )
    except Exception:
        logger.exception("[BATTLE] generate failed")
        await message.answer("😔 Не удалось. Попробуй позже.")
        return

    if result is None:
        await message.answer("😔 Не удалось. Попробуй позже.")
        return

    text = format_photo_battle(result)

    # Кнопки
    rows = []
    if result.get("allowed") and not result.get("is_pro"):
        rows.append([InlineKeyboardButton(
            text="💎 Открыть полный разбор",
            callback_data="pro_menu",
        )])
    rows.append([InlineKeyboardButton(
        text="⚔️ Ещё раз",
        callback_data="hook_compare",
    )])
    rows.append([InlineKeyboardButton(
        text="🔥 Что ещё?",
        callback_data="hook_menu",
    )])
    rows.append([InlineKeyboardButton(
        text="🏠 В главное меню",
        callback_data="back_to_main",
    )])
    kb = InlineKeyboardMarkup(inline_keyboard=rows)

    try:
        await message.answer(text, reply_markup=kb)
    except Exception:
        logger.exception("[BATTLE] send failed")

    try:
        await track(
            "photo_battle_viewed",
            telegram_id=message.from_user.id,
            payload={
                "is_pro": result.get("is_pro", False),
                "allowed": result.get("allowed", False),
                "reason": result.get("reason", ""),
                "winner": result.get("winner", 0),
            },
        )
    except Exception:
        logger.exception("[BATTLE] track failed")


# ============================================================
# ОТМЕНА
# ============================================================
@router.message(
    Command("cancel"),
    StateFilter("photo_battle_first", "photo_battle_second"),
)
async def cancel_battle(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ Сравнение отменено.")