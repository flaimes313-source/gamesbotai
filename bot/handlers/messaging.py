from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select

from database.connection import async_session
from database.models import Message, User
from services.ai.factory import get_ai_provider
from services.jokes import categories, random_joke
from utils.logging import get_logger

router = Router()
logger = get_logger(__name__)


def message_styles_kb(target_user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="👋 Поздороваться", callback_data=f"style_friendly_{target_user_id}")],
            [InlineKeyboardButton(text="😎 Уверенно", callback_data=f"style_confident_{target_user_id}")],
            [InlineKeyboardButton(text="😂 С юмором", callback_data=f"style_funny_{target_user_id}")],
            [InlineKeyboardButton(text="🧠 Задать вопрос", callback_data=f"style_interesting_{target_user_id}")],
            [InlineKeyboardButton(text="🎯 Зацепить", callback_data=f"style_provocative_{target_user_id}")],
        ]
    )


def jokes_categories_kb(target_user_id: int) -> InlineKeyboardMarkup:
    cats = categories()
    rows = [
        [InlineKeyboardButton(text=f"📂 {c}", callback_data=f"jokecat_{c}_{target_user_id}")]
        for c in cats
    ]
    rows.append([InlineKeyboardButton(text="🎲 Случайный", callback_data=f"jokecat_random_{target_user_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data.startswith("msg_"))
async def cb_msg(callback: CallbackQuery):
    await callback.answer()
    target_id = int(callback.data.replace("msg_", ""))
    await callback.message.answer(
        "Выбери стиль первого сообщения:",
        reply_markup=message_styles_kb(target_id),
    )


@router.callback_query(F.data.startswith("style_"))
async def cb_style(callback: CallbackQuery):
    await callback.answer("Генерирую варианты...")
    _, style, target_id_str = callback.data.split("_", 2)
    target_id = int(target_id_str)

    async with async_session() as session:
        me = (await session.execute(select(User).where(User.telegram_id == callback.from_user.id))).scalar_one_or_none()
        target = (await session.execute(select(User).where(User.id == target_id))).scalar_one_or_none()

    if not me or not target:
        await callback.message.answer("Ошибка поиска игрока.")
        return

    try:
        result = await get_ai_provider().generate_message_suggestions(
            my_archetype="Игрок",
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

    lines = ["💬 Варианты первого сообщения:"]
    for i, m in enumerate(msgs, 1):
        lines.append(f"{i}. {m}")
    await callback.message.answer("\n".join(lines))


@router.callback_query(F.data.startswith("joke_"))
async def cb_joke(callback: CallbackQuery):
    await callback.answer()
    target_id = int(callback.data.replace("joke_", ""))
    await callback.message.answer(
        "😄 Выбери категорию прикола:",
        reply_markup=jokes_categories_kb(target_id),
    )


@router.callback_query(F.data.startswith("jokecat_"))
async def cb_jokecat(callback: CallbackQuery):
    await callback.answer()
    _, category, target_id_str = callback.data.split("_", 2)
    target_id = int(target_id_str)

    joke = random_joke(None if category == "random" else category)

    async with async_session() as session:
        me = (await session.execute(select(User).where(User.telegram_id == callback.from_user.id))).scalar_one_or_none()
        if me:
            session.add(Message(sender_id=me.id, receiver_id=target_id, type="joke", text=joke))
            await session.commit()

    await callback.message.answer(f"😂 Отправлено:\n\n{joke}")