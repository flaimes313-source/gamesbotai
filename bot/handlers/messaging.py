from typing import Dict

from aiogram import F, Router
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy import select

from database.connection import async_session
from database.models import User
from services.access import has_full_access
from services.ai.factory import get_ai_provider
from services.analytics.tracker import track
from services.chats import get_or_create_chat, send_chat_message
from services.feature_flags import is_enabled
from services.jokes import categories, random_joke
from utils.logging import get_logger

router = Router()
logger = get_logger(__name__)

_SUGGESTIONS: Dict[str, dict] = {}


def message_styles_kb(target_user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="👋 Поздороваться", callback_data=f"style_friendly_{target_user_id}")],
            [InlineKeyboardButton(text="😎 Уверенно", callback_data=f"style_confident_{target_user_id}")],
            [InlineKeyboardButton(text="😂 С юмором", callback_data=f"style_funny_{target_user_id}")],
            [InlineKeyboardButton(text="🧠 Задать вопрос", callback_data=f"style_interesting_{target_user_id}")],
            [InlineKeyboardButton(text="🎯 Зацепить", callback_data=f"style_provocative_{target_user_id}")],
            [InlineKeyboardButton(text="✍️ Написать своё", callback_data=f"style_custom_{target_user_id}")],
        ]
    )


def jokes_categories_kb(target_user_id: int) -> InlineKeyboardMarkup:
    try:
        cats = categories()
        cats = [c for c in cats if c.lower() not in ("случайный", "random")]
    except Exception:
        logger.exception("Failed to load joke categories")
        cats = []

    rows = [
        [InlineKeyboardButton(text=f"📂 {c}", callback_data=f"jokecat_{c}_{target_user_id}")]
        for c in cats
    ]
    rows.append([InlineKeyboardButton(
        text="🎲 Случайный",
        callback_data=f"jokecat_random_{target_user_id}",
    )])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ============================================================
# CALLBACK: СООБЩЕНИЕ ИГРОКУ
# ============================================================
@router.callback_query(F.data.startswith("msg_"))
async def cb_msg(callback: CallbackQuery):
    await callback.answer()
    target_id = int(callback.data.replace("msg_", ""))

    async with async_session() as session:
        target = (await session.execute(
            select(User).where(User.id == target_id)
        )).scalar_one_or_none()

    if target is None:
        await callback.message.answer("Игрок не найден.")
        return
    if not target.allow_messages:
        await callback.message.answer("🚫 Этот игрок отключил сообщения.")
        return

    await callback.message.answer(
        "Выбери стиль первого сообщения:",
        reply_markup=message_styles_kb(target_id),
    )


@router.callback_query(F.data.startswith("style_custom_"))
async def cb_style_custom(callback: CallbackQuery):
    await callback.answer()
    target_id = int(callback.data.replace("style_custom_", ""))

    async with async_session() as session:
        me = (await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )).scalar_one_or_none()
        if me is None:
            await callback.message.answer("Сначала отправь фото!")
            return
        chat = await get_or_create_chat(session, me.id, target_id)

    from bot.handlers.chats import PENDING_CHAT_REPLY
    PENDING_CHAT_REPLY[callback.from_user.id] = chat.id

    await callback.message.answer(
        "✍️ Напиши своё сообщение одним текстом — оно уйдёт в чат.\n\n"
        "Чтобы отменить — /cancel"
    )


@router.callback_query(F.data.startswith("style_"))
async def cb_style(callback: CallbackQuery):
    await callback.answer("Генерирую варианты...")
    parts = callback.data.split("_", 2)
    if len(parts) < 3:
        return
    _, style, target_id_str = parts
    target_id = int(target_id_str)

    async with async_session() as session:
        me = (await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )).scalar_one_or_none()
        target = (await session.execute(
            select(User).where(User.id == target_id)
        )).scalar_one_or_none()

    if not me or not target:
        await callback.message.answer("Ошибка поиска игрока.")
        return

    try:
        from services.matching.matcher import get_my_profile
        async with async_session() as session:
            my_p = await get_my_profile(session, me.id)

        provider = await get_ai_provider()
        result = await provider.generate_message_suggestions(
            my_archetype=my_p.archetype if my_p else "Игрок",
            their_archetype="Игрок",
            match_score=80,
            style=style,
        )
    except Exception:
        logger.exception("Message suggestions failed")
        result = {"messages": ["Привет! Как настроение?", "Что нового?", "Ты как? 😎"]}

    msgs = result.get("messages", [])
    if not msgs:
        await callback.message.answer("Не удалось сгенерировать. Попробуй позже.")
        return

    full = await has_full_access(callback.from_user.id)
    extra_hint = ""

    if not full:
        msgs = msgs[:1]
        extra_hint = "\n\n💎 С PRO — все 3 варианта на выбор."

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"{i+1}. {m[:40]}", callback_data=f"send_sugg_{target_id}_{i}")]
            for i, m in enumerate(msgs)
        ]
    )

    _SUGGESTIONS[f"sugg_{callback.from_user.id}"] = {
        "target_id": target_id,
        "messages": msgs,
    }

    lines = ["💬 Варианты первого сообщения (нажми, чтобы отправить):"]
    for i, m in enumerate(msgs, 1):
        lines.append(f"{i}. {m}")

    await callback.message.answer("\n".join(lines) + extra_hint, reply_markup=kb)


@router.callback_query(F.data.startswith("send_sugg_"))
async def cb_send_sugg(callback: CallbackQuery):
    await callback.answer("Отправляю...")
    parts = callback.data.split("_")
    if len(parts) < 4:
        return
    target_id = int(parts[2])
    idx = int(parts[3])

    payload = _SUGGESTIONS.pop(f"sugg_{callback.from_user.id}", None)
    if not payload:
        await callback.message.answer("Варианты устарели. Запроси заново.")
        return

    msg_text = payload["messages"][idx]

    async with async_session() as session:
        me = (await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )).scalar_one_or_none()
        if me is None:
            await callback.message.answer("Сначала отправь фото!")
            return
        chat = await get_or_create_chat(session, me.id, target_id)

    result = await send_chat_message(
        bot=callback.bot,
        sender_telegram_id=callback.from_user.id,
        chat_id=chat.id,
        text=msg_text,
        msg_type="text",
    )

    if result:
        await track("chat_message_sent", telegram_id=callback.from_user.id, payload={"type": "suggestion"})
        await callback.message.answer(
            f"✅ Отправлено:\n\n<i>{msg_text}</i>",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="📜 Открыть чат", callback_data=f"chat_open_{chat.id}")],
                ]
            ),
        )
    else:
        await callback.message.answer("❌ Не удалось доставить.")


# ============================================================
# CALLBACK: ПРИКОЛЫ
# ============================================================
@router.callback_query(F.data.startswith("joke_"))
async def cb_joke(callback: CallbackQuery):
    logger.info(f"Joke button pressed by {callback.from_user.id}: {callback.data}")
    try:
        await callback.answer()
    except Exception:
        pass

    target_id_str = callback.data.replace("joke_", "")
    try:
        target_id = int(target_id_str)
    except ValueError:
        await callback.message.answer("Некорректный игрок.")
        return

    async with async_session() as session:
        target = (await session.execute(
            select(User).where(User.id == target_id)
        )).scalar_one_or_none()

    if target is None:
        await callback.message.answer("Игрок не найден.")
        return

    if not target.allow_messages:
        await callback.message.answer("🚫 Этот игрок отключил сообщения.")
        return

    try:
        kb = jokes_categories_kb(target_id)
    except Exception:
        logger.exception("Failed to build jokes keyboard")
        await callback.message.answer("😔 Приколы временно недоступны. Попробуй позже.")
        return

    await callback.message.answer(
        "😄 Выбери категорию прикола:",
        reply_markup=kb,
    )


@router.callback_query(F.data.startswith("jokecat_"))
async def cb_jokecat(callback: CallbackQuery):
    logger.info(f"Joke category selected by {callback.from_user.id}: {callback.data}")
    try:
        await callback.answer()
    except Exception:
        pass

    parts = callback.data.split("_", 2)
    if len(parts) < 3:
        await callback.message.answer("Ошибка: неверный формат.")
        return

    _, category, target_id_str = parts
    try:
        target_id = int(target_id_str)
    except ValueError:
        await callback.message.answer("Некорректный игрок.")
        return

    try:
        joke = random_joke(None if category == "random" else category)
    except Exception:
        logger.exception("Failed to get joke")
        await callback.message.answer("😔 Приколы временно недоступны.")
        return

    if not joke:
        joke = "😂"

    async with async_session() as session:
        me = (await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )).scalar_one_or_none()
        if me is None:
            await callback.message.answer("Сначала отправь фото!")
            return
        chat = await get_or_create_chat(session, me.id, target_id)

    result = await send_chat_message(
        bot=callback.bot,
        sender_telegram_id=callback.from_user.id,
        chat_id=chat.id,
        text=joke,
        msg_type="joke",
    )

    if result:
        await track("joke_sent", telegram_id=callback.from_user.id, payload={"category": category})
        await callback.message.answer(
            f"😂 Отправлено:\n\n{joke}",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="📜 Открыть чат", callback_data=f"chat_open_{chat.id}")],
                ]
            ),
        )
    else:
        await callback.message.answer("❌ Не удалось доставить.")