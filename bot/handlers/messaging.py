from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select

from database.connection import async_session
from database.models import User
from services.ai.factory import get_ai_provider
from services.jokes import categories, random_joke
from services.messaging import deliver_message, get_inbox
from utils.logging import get_logger

router = Router()
logger = get_logger(__name__)

# Ожидание текста от пользователя: telegram_id → target_user_id
PENDING_REPLY: dict[int, int] = {}


def message_styles_kb(target_user_id: int):
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
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


def jokes_categories_kb(target_user_id: int):
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    rows = [
        [InlineKeyboardButton(text=f"📂 {c}", callback_data=f"jokecat_{c}_{target_user_id}")]
        for c in categories()
    ]
    rows.append([InlineKeyboardButton(text="🎲 Случайный", callback_data=f"jokecat_random_{target_user_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ============================================================
# СООБЩЕНИЯ
# ============================================================
@router.callback_query(F.data.startswith("msg_"))
async def cb_msg(callback: CallbackQuery):
    await callback.answer()
    target_id = int(callback.data.replace("msg_", ""))

    # проверяем, что получатель разрешает сообщения
    async with async_session() as session:
        target = (await session.execute(select(User).where(User.id == target_id))).scalar_one_or_none()
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
    PENDING_REPLY[callback.from_user.id] = target_id
    await callback.message.answer(
        "✍️ Напиши своё сообщение одним текстом. Оно будет доставлено получателю."
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
        me = (await session.execute(select(User).where(User.telegram_id == callback.from_user.id))).scalar_one_or_none()
        target = (await session.execute(select(User).where(User.id == target_id))).scalar_one_or_none()

    if not me or not target:
        await callback.message.answer("Ошибка поиска игрока.")
        return

    try:
        from services.matching.matcher import get_my_profile
        async with async_session() as session:
            my_p = await get_my_profile(session, me.id)
        result = await get_ai_provider().generate_message_suggestions(
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

    # Сохраняем выбор: chat_id → list of (index, text)
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"{i+1}. {m[:40]}", callback_data=f"send_sugg_{target_id}_{i}")]
            for i, m in enumerate(msgs)
        ]
    )

    # сохраняем варианты в памяти
    PENDING_REPLY[f"sugg_{callback.from_user.id}"] = {"target_id": target_id, "messages": msgs}

    lines = ["💬 Варианты первого сообщения (нажми, чтобы отправить):"]
    for i, m in enumerate(msgs, 1):
        lines.append(f"{i}. {m}")
    await callback.message.answer("\n".join(lines), reply_markup=kb)


@router.callback_query(F.data.startswith("send_sugg_"))
async def cb_send_sugg(callback: CallbackQuery):
    await callback.answer("Отправляю...")
    parts = callback.data.split("_")
    if len(parts) < 4:
        return
    target_id = int(parts[2])
    idx = int(parts[3])

    payload = PENDING_REPLY.pop(f"sugg_{callback.from_user.id}", None)
    if not payload:
        await callback.message.answer("Варианты устарели. Запроси заново.")
        return

    msg_text = payload["messages"][idx]

    ok = await deliver_message(
        bot=callback.bot,
        sender_telegram_id=callback.from_user.id,
        receiver_user_id=target_id,
        text=msg_text,
        msg_type="text",
    )

    if ok:
        await callback.message.answer(f"✅ Отправлено:\n\n<i>{msg_text}</i>")
    else:
        await callback.message.answer("❌ Не удалось доставить. Возможно, получатель отключил сообщения.")


@router.message(F.text & ~F.text.startswith("/"))
async def handle_custom_text(message: Message):
    """Обрабатывает текст от пользователя, если он ждёт отправки сообщения."""
    target_id = PENDING_REPLY.get(message.from_user.id)
    if not target_id:
        return  # не наш случай

    PENDING_REPLY.pop(message.from_user.id, None)

    ok = await deliver_message(
        bot=message.bot,
        sender_telegram_id=message.from_user.id,
        receiver_user_id=target_id,
        text=message.text[:1000],
        msg_type="text",
    )

    if ok:
        await message.answer("✅ Сообщение доставлено!")
    else:
        await message.answer("❌ Не удалось доставить. Возможно, получатель отключил сообщения.")


# ============================================================
# ПРИКОЛЫ
# ============================================================
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
    parts = callback.data.split("_", 2)
    if len(parts) < 3:
        return
    _, category, target_id_str = parts
    target_id = int(target_id_str)

    joke = random_joke(None if category == "random" else category)

    ok = await deliver_message(
        bot=callback.bot,
        sender_telegram_id=callback.from_user.id,
        receiver_user_id=target_id,
        text=joke,
        msg_type="joke",
    )

    if ok:
        await callback.message.answer(f"😂 Отправлено:\n\n{joke}")
    else:
        await callback.message.answer("❌ Не доставлено.")


# ============================================================
# INBOX
# ============================================================
@router.message(F.text == "📬 Входящие")
async def show_inbox(message: Message):
    msgs = await get_inbox(message.from_user.id, limit=10)
    if not msgs:
        await message.answer("📭 Входящих пока нет.")
        return

    lines = ["📬 <b>Последние входящие:</b>\n"]
    for m in msgs:
        handle = f"@{m['sender_username']}" if m["sender_username"] else m["sender_name"]
        prefix = "😂" if m["type"] == "joke" else "💬"
        lines.append(f"{prefix} <b>{handle}</b>: {m['text'][:120]}")
    await message.answer("\n".join(lines))