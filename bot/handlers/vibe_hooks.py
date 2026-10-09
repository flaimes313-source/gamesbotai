"""
Крючки после анализа (Этап A + B + C + D).

Этап A: показ раз в 3 дня + кнопка «🔥 Что ещё?».
Этап B: «Какой ты сегодня?» — AI.
Этап C: «Что обо мне думают?» — AI.
Этап D: «Сравнение 2 фото» — FSM.
Заглушки: E, F — «Скоро».
"""

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select

from database.connection import async_session
from database.models import User
from services.analytics.tracker import track
from utils.logging import get_logger

router = Router()
logger = get_logger(__name__)


# ============================================================
# ЗАГЛУШКИ E / F
# ============================================================
HOOK_TEXTS = {
    "best_photo": {
        "title": "🏆 Выбрать лучшее фото",
        "text": (
            "🏆 <b>Выбрать лучшее фото</b>\n\n"
            "Отправь 3 фото — Вайбми выберет лучшее.\n\n"
            "И скажет, какое подходит для:\n"
            "• Telegram\n"
            "• знакомств\n"
            "• делового профиля\n\n"
            "🛠 <b>Скоро в Вайбми.</b>"
        ),
    },
    "ai_friend": {
        "title": "🤖 AI-друг",
        "text": (
            "🤖 <b>AI-друг</b>\n\n"
            "Личный AI, который знает твой вайб.\n\n"
            "Он понимает:\n"
            "• как ты выглядишь\n"
            "• какой у тебя характер\n"
            "• что тебе подходит\n\n"
            "Обсуждай ситуации, спрашивай совета, "
            "разбирай отношения.\n\n"
            "🛠 <b>Скоро в Вайбми.</b>"
        ),
    },
}


def _back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="🔥 Что ещё?",
                callback_data="hook_menu",
            )],
            [InlineKeyboardButton(
                text="🏠 В главное меню",
                callback_data="back_to_main",
            )],
        ]
    )


def _menu_kb() -> InlineKeyboardMarkup:
    from bot.keyboards.main import first_analysis_kb
    return first_analysis_kb()


# ============================================================
# ОБЩИЙ ОБРАБОТЧИК ЗАГЛУШЕК
# ============================================================
async def _handle_hook(callback: CallbackQuery, hook_key: str) -> None:
    await callback.answer()

    hook = HOOK_TEXTS.get(hook_key)
    if not hook:
        return

    try:
        await callback.message.answer(
            hook["text"],
            reply_markup=_back_kb(),
        )
    except Exception:
        logger.exception(f"[HOOK] failed to send {hook_key}")

    try:
        await track(
            "hook_clicked",
            telegram_id=callback.from_user.id,
            payload={"hook": hook_key},
        )
    except Exception:
        logger.exception("[HOOK] track failed")


# ============================================================
# ЭТАП B — «Какой ты сегодня?»
# ============================================================
@router.callback_query(F.data == "hook_today")
async def cb_hook_today(callback: CallbackQuery):
    await callback.answer("Анализирую твой вайб...")

    async with async_session() as session:
        user = (await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )).scalar_one_or_none()

    if user is None:
        await callback.message.answer("Сначала отправь фото — я должен знать твой вайб!")
        return

    try:
        from services.analysis.today_vibe import (
            generate_today_vibe_for_user,
            format_today_vibe,
        )
        result = await generate_today_vibe_for_user(user.id, callback.from_user.id)
    except Exception:
        logger.exception("[HOOK] today_vibe failed")
        await callback.message.answer("😔 Не удалось. Попробуй позже.")
        return

    if result is None:
        await callback.message.answer("😔 Не удалось. Попробуй позже.")
        return

    text = format_today_vibe(result)

    rows = []
    if not result.get("is_pro") and result.get("allowed"):
        rows.append([InlineKeyboardButton(
            text="💎 Открыть полный разбор",
            callback_data="pro_menu",
        )])
    rows.append([InlineKeyboardButton(
        text="🔄 Ещё раз",
        callback_data="hook_today",
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
        await callback.message.answer(text, reply_markup=kb)
    except Exception:
        logger.exception("[HOOK] send failed")

    try:
        await track(
            "today_vibe_viewed",
            telegram_id=callback.from_user.id,
            payload={
                "is_pro": result.get("is_pro", False),
                "allowed": result.get("allowed", False),
                "reason": result.get("reason", ""),
            },
        )
    except Exception:
        logger.exception("[HOOK] track failed")


# ============================================================
# ЭТАП C — «Что обо мне думают?»
# ============================================================
@router.callback_query(F.data == "hook_impression")
async def cb_hook_impression(callback: CallbackQuery):
    await callback.answer("Смотрю глазами незнакомца...")

    async with async_session() as session:
        user = (await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )).scalar_one_or_none()

    if user is None:
        await callback.message.answer("Сначала отправь фото — я должен знать твой вайб!")
        return

    try:
        from services.analysis.first_impression import (
            generate_first_impression_for_user,
            format_first_impression,
        )
        result = await generate_first_impression_for_user(user.id, callback.from_user.id)
    except Exception:
        logger.exception("[HOOK] first_impression failed")
        await callback.message.answer("😔 Не удалось. Попробуй позже.")
        return

    if result is None:
        await callback.message.answer("😔 Не удалось. Попробуй позже.")
        return

    text = format_first_impression(result)

    rows = []
    if not result.get("is_pro") and result.get("allowed"):
        rows.append([InlineKeyboardButton(
            text="💎 Открыть полный разбор",
            callback_data="pro_menu",
        )])
    rows.append([InlineKeyboardButton(
        text="🔄 Ещё раз",
        callback_data="hook_impression",
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
        await callback.message.answer(text, reply_markup=kb)
    except Exception:
        logger.exception("[HOOK] send failed")

    try:
        await track(
            "first_impression_viewed",
            telegram_id=callback.from_user.id,
            payload={
                "is_pro": result.get("is_pro", False),
                "allowed": result.get("allowed", False),
                "reason": result.get("reason", ""),
            },
        )
    except Exception:
        logger.exception("[HOOK] track failed")


# ============================================================
# ЭТАП D — «Сравнение 2 фото» (FSM-запуск)
# ============================================================
@router.callback_query(F.data == "hook_compare")
async def cb_hook_compare(callback: CallbackQuery, state: FSMContext):
    await callback.answer()

    async with async_session() as session:
        user = (await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )).scalar_one_or_none()

    if user is None:
        await callback.message.answer("Сначала отправь фото — я должен знать твой вайб!")
        return

    # Проверка лимита + сразу сохраняем user_id
    from services.analysis.photo_battle import _check_limit
    allowed, is_pro = await _check_limit(user.id, callback.from_user.id)
    if not allowed:
        await callback.message.answer(
            "⚔️ <b>Сравнение 2 фото</b>\n\n"
            "Ты уже использовал бесплатное сравнение на сегодня.\n\n"
            "💎 <b>С Pro — безлимит.</b>",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="💎 Pro", callback_data="pro_menu")],
                [InlineKeyboardButton(text="🏠 В меню", callback_data="back_to_main")],
            ]),
        )
        return

    # Сохраняем состояние
    await state.set_state("photo_battle_first")
    await state.update_data(user_id=user.id, is_pro=is_pro)

    await callback.message.answer(
        "⚔️ <b>БИТВА ВАЙБОВ</b>\n\n"
        "Отправь <b>первое фото</b> — а потом второе.\n\n"
        "<i>Можно отменить командой /cancel.</i>"
    )


# ============================================================
# ЗАГЛУШКИ E / F
# ============================================================
@router.callback_query(F.data == "hook_best_photo")
async def cb_hook_best_photo(callback: CallbackQuery):
    await _handle_hook(callback, "best_photo")


@router.callback_query(F.data == "hook_ai_friend")
async def cb_hook_ai_friend(callback: CallbackQuery):
    await _handle_hook(callback, "ai_friend")


# ============================================================
# МЕНЮ КРЮЧКОВ
# ============================================================
@router.callback_query(F.data == "hook_menu")
async def cb_hook_menu(callback: CallbackQuery):
    await callback.answer()
    try:
        await callback.message.answer(
            "🔥 <b>Что ещё интересно?</b>\n\nВыбери:",
            reply_markup=_menu_kb(),
        )
    except Exception:
        logger.exception("[HOOK] failed to show menu")