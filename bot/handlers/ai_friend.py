"""
FSM-режим «AI-друг» (Этап F).

Состояние:
- ai_friend_active — юзер в режиме AI-друга, любое текстовое сообщение
  уходит AI.

Вход:
- Reply-кнопка «🤖 AI-друг» (главное меню).
- Callback hook_ai_friend (из крючков).

Выход: /exit или inline-кнопка «🚪 Выйти».
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
from sqlalchemy import select

from database.connection import async_session
from database.models import User
from services.analytics.tracker import track
from utils.logging import get_logger

router = Router()
logger = get_logger(__name__)


# ============================================================
# ВСПОМОГАТЕЛЬНЫЕ КЛАВИАТУРЫ
# ============================================================
def _exit_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="🚪 Выйти из чата",
                callback_data="ai_friend_exit",
            )],
            [InlineKeyboardButton(
                text="🗑 Очистить историю",
                callback_data="ai_friend_clear",
            )],
        ]
    )


def _clear_confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="🗑 Да, удалить всё",
                callback_data="ai_friend_clear_yes",
            )],
            [InlineKeyboardButton(
                text="⬅️ Отмена",
                callback_data="ai_friend_clear_no",
            )],
        ]
    )


# ============================================================
# ВХОД: Reply-кнопка «🤖 AI-друг»
# ============================================================
@router.message(F.text == "🤖 AI-друг")
async def btn_ai_friend(message: Message, state: FSMContext):
    async with async_session() as session:
        user = (await session.execute(
            select(User).where(User.telegram_id == message.from_user.id)
        )).scalar_one_or_none()

    if user is None:
        await message.answer("Сначала отправь фото — я должен знать твой вайб!")
        return

    await _start_ai_friend(
        user_id=user.id,
        telegram_id=message.from_user.id,
        message=message,
        state=state,
    )


# ============================================================
# ВХОД: callback hook_ai_friend (из крючков)
# ============================================================
@router.callback_query(F.data == "hook_ai_friend")
async def cb_hook_ai_friend(callback: CallbackQuery, state: FSMContext):
    await callback.answer()

    async with async_session() as session:
        user = (await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )).scalar_one_or_none()

    if user is None:
        await callback.message.answer("Сначала отправь фото — я должен знать твой вайб!")
        return

    await _start_ai_friend(
        user_id=user.id,
        telegram_id=callback.from_user.id,
        message=callback.message,
        state=state,
    )


# ============================================================
# ОБЩИЙ ЗАПУСК
# ============================================================
async def _start_ai_friend(
    user_id: int,
    telegram_id: int,
    message: Message,
    state: FSMContext,
) -> None:
    from services.analysis.ai_friend import (
        check_ai_friend_limit,
        collect_profile_data,
        count_history,
    )
    allowed, is_pro, remaining = await check_ai_friend_limit(
        user_id, telegram_id
    )

    profile_data = await collect_profile_data(user_id)
    if profile_data is None:
        await message.answer("Сначала отправь фото — я должен знать твой вайб!")
        return

    history_count = await count_history(user_id)

    from prompts.ai_friend import AI_FRIEND_FIRST_MESSAGE

    # Если лимит уже исчерпан — не пускаем
    if not allowed:
        await message.answer(
            "🤖 <b>AI-друг</b>\n\n"
            "На сегодня сообщения закончились.\n\n"
            "💎 <b>С Pro — безлимит.</b>",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="💎 Pro", callback_data="pro_menu")],
                [InlineKeyboardButton(text="🏠 В меню", callback_data="back_to_main")],
            ]),
        )
        return

    # Формируем приветствие
    if history_count > 0:
        first_text = (
            f"🤖 <b>С возвращением, {profile_data.get('user_name', 'Игрок')}!</b>\n\n"
            f"Я помню нашу переписку ({history_count} сообщ.). "
            "Продолжаем?\n\n"
            "<i>Команда /exit — выйти. Кнопка 🗑 — очистить историю.</i>"
        )
    else:
        first_text = AI_FRIEND_FIRST_MESSAGE.format(
            user_name=profile_data.get("user_name", "Игрок"),
            archetype=profile_data.get("archetype", "загадочный тип"),
        )
        first_text += "\n\n<i>Команда /exit — выйти из чата.</i>"

    await state.set_state("ai_friend_active")
    await state.update_data(user_id=user_id)

    try:
        await message.answer(first_text, reply_markup=_exit_kb())
    except Exception:
        logger.exception("[AI_FRIEND] first message failed")

    try:
        await track(
            "ai_friend_started",
            telegram_id=telegram_id,
            payload={
                "is_pro": is_pro,
                "remaining": remaining,
                "history_count": history_count,
            },
        )
    except Exception:
        logger.exception("[AI_FRIEND] track started failed")


# ============================================================
# ВЫХОД
# ============================================================
@router.message(Command("exit"), StateFilter("ai_friend_active"))
async def cmd_exit(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "👋 Ок, вышли из режима AI-друга.\n\n"
        "Вернуться можно кнопкой «🤖 AI-друг»."
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
            "Вернуться можно кнопкой «🤖 AI-друг»."
        )
    except Exception:
        logger.exception("[AI_FRIEND] cb_exit send failed")

    try:
        await track("ai_friend_exited", telegram_id=callback.from_user.id)
    except Exception:
        logger.exception("[AI_FRIEND] track exit failed")


# ============================================================
# ОЧИСТКА ИСТОРИИ
# ============================================================
@router.callback_query(F.data == "ai_friend_clear")
async def cb_clear_ask(callback: CallbackQuery):
    await callback.answer()
    try:
        await callback.message.answer(
            "🗑 <b>Очистить историю AI-друга?</b>\n\n"
            "Это удалит все наши сообщения. Отменить нельзя.",
            reply_markup=_clear_confirm_kb(),
        )
    except Exception:
        logger.exception("[AI_FRIEND] clear ask failed")


@router.callback_query(F.data == "ai_friend_clear_yes")
async def cb_clear_yes(callback: CallbackQuery, state: FSMContext):
    await callback.answer("Удаляю…")

    data = await state.get_data()
    user_id = data.get("user_id")

    if not user_id:
        async with async_session() as session:
            user = (await session.execute(
                select(User).where(User.telegram_id == callback.from_user.id)
            )).scalar_one_or_none()
        user_id = user.id if user else None

    if not user_id:
        await callback.message.answer("Сначала отправь фото.")
        return

    deleted = 0
    try:
        from services.analysis.ai_friend import clear_history
        deleted = await clear_history(user_id)
        await callback.message.answer(
            f"🗑 <b>История очищена.</b>\n\n"
            f"Удалено сообщений: <b>{deleted}</b>.\n"
            "Начнём с чистого листа."
        )
    except Exception:
        logger.exception("[AI_FRIEND] clear failed")
        await callback.message.answer("😔 Не удалось очистить.")

    try:
        await track(
            "ai_friend_cleared",
            telegram_id=callback.from_user.id,
            payload={"deleted": deleted},
        )
    except Exception:
        pass


@router.callback_query(F.data == "ai_friend_clear_no")
async def cb_clear_no(callback: CallbackQuery):
    await callback.answer("Отменено")
    try:
        await callback.message.answer("👍 Оставил как есть.")
    except Exception:
        pass


# ============================================================
# ОСНОВНОЙ ОБРАБОТЧИК СООБЩЕНИЙ
# ============================================================
@router.message(F.text, StateFilter("ai_friend_active"))
async def handle_message(message: Message, state: FSMContext):
    user_text = (message.text or "").strip()
    if not user_text:
        return

    # Пропускаем команды — их ловят другие хендлеры
    if user_text.startswith("/"):
        return

    data = await state.get_data()
    user_id = data.get("user_id")

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