"""
FSM-хендлер «Выбрать лучшее фото» (Этап E).

Состояния:
- best_photo_1 — ждём 1-е фото.
- best_photo_2 — ждём 2-е фото.
- best_photo_3 — ждём 3-е фото.

Запускается из vibe_hooks.cb_hook_best_photo (callback hook_best_photo).
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
@router.message(F.photo, StateFilter("best_photo_1"))
async def handle_first_photo(message: Message, state: FSMContext):
    try:
        image = await _download_photo(message)
    except Exception:
        logger.exception("[BEST] first photo download failed")
        await message.answer("😔 Не удалось скачать фото. Попробуй ещё раз.")
        return

    await state.update_data(image_1=image)
    await state.set_state("best_photo_2")

    await message.answer(
        "✅ Фото 1/3 принято.\n\n"
        "Отправь <b>второе фото</b>."
    )


# ============================================================
# ШАГ 2: ВТОРОЕ ФОТО
# ============================================================
@router.message(F.photo, StateFilter("best_photo_2"))
async def handle_second_photo(message: Message, state: FSMContext):
    try:
        image = await _download_photo(message)
    except Exception:
        logger.exception("[BEST] second photo download failed")
        await message.answer("😔 Не удалось скачать фото. Попробуй ещё раз.")
        return

    await state.update_data(image_2=image)
    await state.set_state("best_photo_3")

    await message.answer(
        "✅ Фото 2/3 принято.\n\n"
        "Отправь <b>третье фото</b>."
    )


# ============================================================
# ШАГ 3: ТРЕТЬЕ ФОТО → AI
# ============================================================
@router.message(F.photo, StateFilter("best_photo_3"))
async def handle_third_photo(message: Message, state: FSMContext):
    data = await state.get_data()
    image_1 = data.get("image_1")
    image_2 = data.get("image_2")
    user_id = data.get("user_id")

    if not image_1 or not image_2 or not user_id:
        await state.clear()
        await message.answer("❌ Что-то пошло не так. Начни заново.")
        return

    await message.answer("🏆 Выбираю лучшее фото...")

    try:
        image_3 = await _download_photo(message)
    except Exception:
        logger.exception("[BEST] third photo download failed")
        await message.answer("😔 Не удалось скачать фото. Попробуй ещё раз.")
        await state.clear()
        return

    await state.clear()

    try:
        from services.analysis.best_photo import (
            generate_best_photo_for_user,
            format_best_photo,
        )
        result = await generate_best_photo_for_user(
            user_id=user_id,
            telegram_id=message.from_user.id,
            image_1_bytes=image_1,
            image_2_bytes=image_2,
            image_3_bytes=image_3,
        )
    except Exception:
        logger.exception("[BEST] generate failed")
        await message.answer("😔 Не удалось. Попробуй позже.")
        return

    if result is None:
        await message.answer("😔 Не удалось. Попробуй позже.")
        return

    text = format_best_photo(result)

    rows = []
    if result.get("allowed") and not result.get("is_pro"):
        rows.append([InlineKeyboardButton(
            text="💎 Открыть полный разбор",
            callback_data="pro_menu",
        )])
    rows.append([InlineKeyboardButton(
        text="🏆 Ещё раз",
        callback_data="hook_best_photo",
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
        logger.exception("[BEST] send failed")

    try:
        await track(
            "best_photo_viewed",
            telegram_id=message.from_user.id,
            payload={
                "is_pro": result.get("is_pro", False),
                "allowed": result.get("allowed", False),
                "reason": result.get("reason", ""),
                "winner": result.get("winner", 0),
            },
        )
    except Exception:
        logger.exception("[BEST] track failed")


# ============================================================
# ОТМЕНА
# ============================================================
@router.message(
    Command("cancel"),
    StateFilter("best_photo_1", "best_photo_2", "best_photo_3"),
)
async def cancel_best_photo(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ Выбор лучшего фото отменён.")