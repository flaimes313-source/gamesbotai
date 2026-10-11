"""
FSM-режим «AI-друг» (Этап F).

Состояние:
- ai_friend_active — юзер в режиме AI-друга, любое текстовое сообщение
  уходит AI.

Вход: vibe_hooks.cb_hook_ai_friend.
Выход: /exit или inline-кнопка.
"""

from aiogram import F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from services.analytics.tracker import track
from utils.logging import get_logger

router = Router()
logger = get_logger(__name__)


# ============================================================
# ВСПОМОГАТЕЛЬНОЕ: клавиатура под ответами
# ============================================================
def _exit_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="🚪 Выйти из чата",
                callback_data="ai_friend_exit",
            )],
        ]
    )


# ============================================================
# ВЫХОД
# ============================================================
@router.message(Command("exit"), StateFilter("ai_friend_active"))
async def cmd_exit(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "👋 Ок, вышли из режима AI-друга.\n\n"
        "Вернуться можно через кнопку «🤖 AI-друг»."
    )
    try:
        await track("ai_friend_exited", telegram_id=message.from_user.id)
    except Exception:
        logger.exception("[AI_FRIEND] track exit failed")


@router.callback_query(F.data == "ai_friend_exit")
async def cb_exit(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    try:
        await callback.message.answer(
            "👋 Вышли из режима AI-друга.\n\n"
            "Вернуться можно через кнопку «🤖 AI-друг»."
        )
    except Exception:
        logger.exception("[AI_FRIEND] cb_exit send failed")

    try:
        await track("ai_friend_exited", telegram_id=callback.from_user.id)
    except Exception:
        logger.exception("[AI_FRIEND] track exit failed")


# ============================================================
# ОСНОВНОЙ ОБРАБОТЧИК СООБЩЕНИЙ
# ============================================================
@router.message(F.text, StateFilter("ai_friend_active"))
async def handle_message(message: Message, state: FSMContext):
    user_text = (message.text or "").strip()
    if not user_text:
        return

    # Достаём user_id и историю из FSM
    data = await state.get_data()
    user_id = data.get("user_id")
    history = data.get("history") or []

    if not user_id:
        await state.clear()
        await message.answer("❌ Что-то пошло не так. Зайди заново через «🤖 AI-друг».")
        return

    await message.answer("💭 Думаю...")

    try:
        from services.analysis.ai_friend import generate_ai_friend_reply
        result = await generate_ai_friend_reply(
            user_id=user_id,
            telegram_id=message.from_user.id,
            history=history,
            user_message=user_text,
        )
    except Exception:
        logger.exception("[AI_FRIEND] generate failed")
        await message.answer("😔 Не удалось. Попробуй позже.")
        return

    if not result.get("allowed"):
        reason = result.get("reason")
        if reason == "limit_reached":
            await message.answer(
                "🤖 <b>На сегодня хватит.</b>\n\n"
                "Free-режим: 3 сообщения в день.\n\n"
                "💎 <b>С Pro — безлимит.</b>",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="💎 Pro", callback_data="pro_menu")],
                    [InlineKeyboardButton(text="🚪 Выйти", callback_data="ai_friend_exit")],
                ]),
            )
            return
        if reason == "no_profile":
            await state.clear()
            await message.answer(
                "Сначала отправь фото — я должен знать твой вайб."
            )
            return
        if reason == "ai_failed":
            await message.answer(
                "😔 AI сейчас перегружен.\n\n"
                "🔁 <b>Сообщение не потрачено.</b>"
            )
            return
        await message.answer("😔 Не получилось. Попробуй позже.")
        return

    reply = result.get("reply", "")
    if not reply:
        await message.answer("😔 Пустой ответ. Попробуй переформулировать.")
        return

    # Обновляем историю (обрезаем до 10)
    history.append({"role": "user", "text": user_text})
    history.append({"role": "assistant", "text": reply})
    history = history[-10:]
    await state.update_data(history=history)

    # Счётчик оставшихся (только Free)
    footer = ""
    if not result.get("is_pro"):
        remaining = result.get("remaining", 0)
        footer = f"\n\n<i>Осталось сообщений сегодня: {remaining}/3</i>"

    try:
        await message.answer(reply + footer, reply_markup=_exit_kb())
    except Exception:
        logger.exception("[AI_FRIEND] send failed")

    try:
        await track(
            "ai_friend_message",
            telegram_id=message.from_user.id,
            payload={
                "is_pro": result.get("is_pro", False),
                "remaining": result.get("remaining", 0),
                "msg_len": len(user_text),
            },
        )
    except Exception:
        logger.exception("[AI_FRIEND] track failed")