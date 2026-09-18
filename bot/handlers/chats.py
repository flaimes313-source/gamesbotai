from typing import Dict

from aiogram import F, Router
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy import select

from bot.keyboards.chats import (
    chat_actions_kb,
    chat_ai_suggestions_kb,
    chat_list_back_kb,
)
from database.connection import async_session
from database.models import Chat, User
from services.access import has_full_access
from services.ai.factory import get_ai_provider
from services.analytics.tracker import track
from services.chats import (
    get_chat_messages,
    get_or_create_chat,
    list_user_chats,
    mark_chat_read,
    send_chat_message,
)
from utils.logging import get_logger

router = Router()
logger = get_logger(__name__)

# Пользователь, ожидающий ввода текста в чат: telegram_id → chat_id
PENDING_CHAT_REPLY: Dict[int, int] = {}


# ============================================================
# Фильтр для catch-all
# ============================================================
def _is_waiting_chat_reply(message: Message) -> bool:
    return PENDING_CHAT_REPLY.get(message.from_user.id) is not None


# ============================================================
# Reply-кнопка «💬 Мои чаты»
# ============================================================
@router.message(F.text == "💬 Мои чаты")
async def show_chats_from_menu(message: Message):
    await _send_chat_list(message, message.from_user.id)


@router.callback_query(F.data == "chat_list")
async def cb_chat_list(callback: CallbackQuery):
    await callback.answer()
    await _send_chat_list(callback, callback.from_user.id)


# ============================================================
# Список чатов
# ============================================================
async def _send_chat_list(message_or_callback, telegram_id: int) -> None:
    await track("chats_list_viewed", telegram_id=telegram_id)

    async with async_session() as session:
        me = (await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )).scalar_one_or_none()

        if me is None:
            return await _reply(message_or_callback, "Сначала отправь фото — создай профиль!", None)

        chats = await list_user_chats(session, me.id, limit=20)

    if not chats:
        text = (
            "💬 <b>Мои чаты</b>\n\n"
            "Пока нет ни одного диалога.\n\n"
            "Найди игроков через «🎯 Найти игроков» и нажми "
            "«💬 Написать сообщение» — так начнётся первый чат."
        )
        return await _reply(message_or_callback, text, chat_list_back_kb())

    lines = ["💬 <b>Мои чаты</b>\n"]
    for c in chats:
        name = c["other_name"]
        if c["show_username"] and c["other_username"]:
            name += f" (@{c['other_username']})"

        last = c["last_text"] or "—"
        if c["last_from_me"]:
            last = "Ты: " + last

        prefix = "🟢" if c["unread_count"] > 0 else "⚪"
        unread_str = f" <b>({c['unread_count']})</b>" if c["unread_count"] else ""

        lines.append(f"{prefix} <b>{name}</b>{unread_str}\n   <i>{last[:80]}</i>")

    text = "\n".join(lines)

    rows = []
    for c in chats:
        unread = f" ({c['unread_count']})" if c["unread_count"] else ""
        label = f"💬 {c['other_name'][:20]}{unread}"
        rows.append([InlineKeyboardButton(
            text=label,
            callback_data=f"chat_open_{c['chat_id']}",
        )])
    rows.append([InlineKeyboardButton(
        text="🏠 В главное меню",
        callback_data="back_to_main",
    )])
    kb = InlineKeyboardMarkup(inline_keyboard=rows)

    await _reply(message_or_callback, text, kb)


# ============================================================
# Открытие чата
# ============================================================
@router.callback_query(F.data.startswith("chat_open_"))
async def cb_chat_open(callback: CallbackQuery):
    await callback.answer()
    chat_id = int(callback.data.replace("chat_open_", ""))
    await _open_chat(callback, callback.from_user.id, chat_id)


async def _open_chat(message_or_callback, telegram_id: int, chat_id: int) -> None:
    async with async_session() as session:
        me = (await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )).scalar_one_or_none()
        if me is None:
            return await _reply(message_or_callback, "Сначала отправь фото!", None)

        chat = (await session.execute(
            select(Chat).where(Chat.id == chat_id)
        )).scalar_one_or_none()
        if chat is None:
            return await _reply(message_or_callback, "Чат не найден.", None)

        if me.id not in (chat.user1_id, chat.user2_id):
            return await _reply(message_or_callback, "Нет доступа к чату.", None)

        other_id = chat.user2_id if chat.user1_id == me.id else chat.user1_id
        other = (await session.execute(
            select(User).where(User.id == other_id)
        )).scalar_one_or_none()
        if other is None:
            return await _reply(message_or_callback, "Собеседник не найден.", None)

        messages = await get_chat_messages(session, chat.id, limit=30)
        await mark_chat_read(session, chat, me.id)

    other_name = other.first_name or "Игрок"
    other_username = other.username if other.show_username else None

    header = f"💬 <b>Чат с {other_name}</b>"
    if other_username:
        header += f" (@{other_username})"
    header += "\n" + "─" * 20 + "\n"

    if not messages:
        body = "<i>Пока нет сообщений. Напиши первым!</i>"
    else:
        body_lines = []
        for m in messages:
            text = m.text or ""
            if m.sender_id == me.id:
                body_lines.append(f"<b>Ты:</b> {text}")
            else:
                body_lines.append(f"<b>{other_name}:</b> {text}")
        body = "\n\n".join(body_lines)

    text = f"{header}{body}"
    if len(text) > 3500:
        text = text[:3500] + "\n\n<i>…история обрезана</i>"

    is_pro = await has_full_access(telegram_id)
    kb = chat_actions_kb(chat.id, other_username, is_pro=is_pro)

    await _reply(message_or_callback, text, kb)


# ============================================================
# Ответ в чате
# ============================================================
@router.callback_query(F.data.startswith("chat_reply_"))
async def cb_chat_reply(callback: CallbackQuery):
    await callback.answer()
    chat_id = int(callback.data.replace("chat_reply_", ""))

    async with async_session() as session:
        me = (await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )).scalar_one_or_none()
        if me is None:
            await callback.message.answer("Сначала отправь фото!")
            return

        chat = (await session.execute(
            select(Chat).where(Chat.id == chat_id)
        )).scalar_one_or_none()
        if chat is None:
            await callback.message.answer("Чат не найден.")
            return

        if me.id not in (chat.user1_id, chat.user2_id):
            await callback.message.answer("Нет доступа к чату.")
            return

    PENDING_CHAT_REPLY[callback.from_user.id] = chat_id

    await callback.message.answer(
        "✍️ Напиши своё сообщение одним текстом — оно уйдёт в чат.\n\n"
        "Чтобы отменить — /cancel"
    )


# ============================================================
# AI: Помоги ответить
# ============================================================
@router.callback_query(F.data.startswith("chat_ai_reply_"))
async def cb_chat_ai_reply(callback: CallbackQuery):
    await callback.answer("Генерирую варианты...")
    chat_id = int(callback.data.replace("chat_ai_reply_", ""))

    if not await has_full_access(callback.from_user.id):
        await callback.message.answer("💎 Функция доступна только с PRO.")
        return

    async with async_session() as session:
        me = (await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )).scalar_one_or_none()
        if me is None:
            return

        chat = (await session.execute(
            select(Chat).where(Chat.id == chat_id)
        )).scalar_one_or_none()
        if chat is None or me.id not in (chat.user1_id, chat.user2_id):
            await callback.message.answer("Чат не найден.")
            return

        other_id = chat.user2_id if chat.user1_id == me.id else chat.user1_id
        other = (await session.execute(
            select(User).where(User.id == other_id)
        )).scalar_one_or_none()

        messages = await get_chat_messages(session, chat.id, limit=10)

    if not messages:
        await callback.message.answer(
            "🤖 Пока нет сообщений для анализа.\n"
            "Напиши первое — потом AI сможет помочь."
        )
        return

    history = []
    for m in messages:
        history.append({
            "from": "me" if m.sender_id == me.id else "them",
            "text": m.text or "",
        })

    my_name = me.first_name or "Ты"
    other_name = other.first_name if other else "Собеседник"

    await callback.message.answer("🤖 Думаю над ответом...")

    try:
        result = await get_ai_provider().generate_chat_reply_suggestions(
            history=history,
            my_name=my_name,
            other_name=other_name,
        )
    except Exception:
        logger.exception("AI chat reply failed")
        await callback.message.answer("😔 AI сейчас не смог подобрать варианты. Попробуй позже.")
        return

    suggestions = result.get("suggestions", [])[:3]
    if not suggestions:
        await callback.message.answer("😔 Не удалось сгенерировать варианты.")
        return

    lines = ["🤖 <b>AI предлагает ответить так:</b>\n"]
    for i, s in enumerate(suggestions, 1):
        lines.append(f"<b>{i}.</b> {s}")

    rows = [
        [InlineKeyboardButton(
            text=f"{i+1}. {s[:35]}{'…' if len(s) > 35 else ''}",
            callback_data=f"chat_ai_send_{chat_id}_{i}",
        )]
        for i, s in enumerate(suggestions)
    ]
    rows.append([InlineKeyboardButton(
        text="⬅️ К чату",
        callback_data=f"chat_open_{chat_id}",
    )])

    # Сохраняем варианты
    from bot.handlers.chats import _AI_SUGGESTIONS
    _AI_SUGGESTIONS[f"ai_{callback.from_user.id}"] = {
        "chat_id": chat_id,
        "suggestions": suggestions,
    }

    await callback.message.answer(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


# Хранилище AI-вариантов: ключ → {chat_id, suggestions}
_AI_SUGGESTIONS: Dict[str, dict] = {}


@router.callback_query(F.data.startswith("chat_ai_send_"))
async def cb_chat_ai_send(callback: CallbackQuery):
    await callback.answer("Отправляю...")
    parts = callback.data.split("_")
    # chat_ai_send_<chat_id>_<idx>
    if len(parts) < 5:
        return
    chat_id = int(parts[3])
    idx = int(parts[4])

    payload = _AI_SUGGESTIONS.pop(f"ai_{callback.from_user.id}", None)
    if not payload:
        await callback.message.answer("Варианты устарели. Запроси заново.")
        return

    suggestions = payload.get("suggestions", [])
    if idx >= len(suggestions):
        await callback.message.answer("Некорректный индекс.")
        return

    msg_text = suggestions[idx]

    result = await send_chat_message(
        bot=callback.bot,
        sender_telegram_id=callback.from_user.id,
        chat_id=chat_id,
        text=msg_text,
        msg_type="text",
    )

    if result:
        await track("chat_ai_sent", telegram_id=callback.from_user.id, payload={"chat_id": chat_id})
        await callback.message.answer(
            f"✅ Отправлено:\n\n<i>{msg_text}</i>",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="📜 Открыть чат", callback_data=f"chat_open_{chat_id}")],
                ]
            ),
        )
    else:
        await callback.message.answer("❌ Не удалось отправить.")


# ============================================================
# AI: Анализ переписки
# ============================================================
@router.callback_query(F.data.startswith("chat_ai_analyze_"))
async def cb_chat_ai_analyze(callback: CallbackQuery):
    await callback.answer("Анализирую...")
    chat_id = int(callback.data.replace("chat_ai_analyze_", ""))

    if not await has_full_access(callback.from_user.id):
        await callback.message.answer("💎 Функция доступна только с PRO.")
        return

    async with async_session() as session:
        me = (await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )).scalar_one_or_none()
        if me is None:
            return

        chat = (await session.execute(
            select(Chat).where(Chat.id == chat_id)
        )).scalar_one_or_none()
        if chat is None or me.id not in (chat.user1_id, chat.user2_id):
            await callback.message.answer("Чат не найден.")
            return

        other_id = chat.user2_id if chat.user1_id == me.id else chat.user1_id
        other = (await session.execute(
            select(User).where(User.id == other_id)
        )).scalar_one_or_none()

        messages = await get_chat_messages(session, chat.id, limit=30)

    if len(messages) < 3:
        await callback.message.answer(
            "📊 Нужно минимум 3 сообщения для анализа. "
            "Продолжайте переписку!"
        )
        return

    history = []
    for m in messages:
        history.append({
            "from": "me" if m.sender_id == me.id else "them",
            "text": m.text or "",
        })

    my_name = me.first_name or "Ты"
    other_name = other.first_name if other else "Собеседник"

    await callback.message.answer("📊 Анализирую переписку...")

    try:
        result = await get_ai_provider().analyze_chat(
            history=history,
            my_name=my_name,
            other_name=other_name,
        )
    except Exception:
        logger.exception("AI chat analysis failed")
        await callback.message.answer("😔 Не удалось проанализировать. Попробуй позже.")
        return

    text = (
        f"📊 <b>Анализ переписки</b>\n\n"
        f"{result.get('emoji', '💬')} <b>Атмосфера:</b> {result.get('vibe', '—')}\n"
        f"🔄 <b>Взаимность:</b> {result.get('mutuality', '—')}\n\n"
        f"💡 <b>Совет:</b> {result.get('advice', '—')}"
    )

    await track("chat_ai_analyzed", telegram_id=callback.from_user.id, payload={"chat_id": chat_id})

    await callback.message.answer(
        text,
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ К чату", callback_data=f"chat_open_{chat_id}")],
            ]
        ),
    )


# ============================================================
# AI: Заглушка для не-PRO
# ============================================================
@router.callback_query(F.data.startswith("chat_ai_locked_"))
async def cb_chat_ai_locked(callback: CallbackQuery):
    await callback.answer()
    await callback.message.answer(
        "💎 <b>AI-помощник доступен только с PRO</b>\n\n"
        "С PRO ты можешь:\n"
        "• 🤖 Получать 3 варианта ответа от AI прямо в чате\n"
        "• 📊 Анализировать переписку (атмосфера, взаимность, совет)\n\n"
        "Оформить: /start → 💎 PRO"
    )


# ============================================================
# /cancel
# ============================================================
@router.message(F.text == "/cancel")
async def cmd_cancel(message: Message):
    if PENDING_CHAT_REPLY.pop(message.from_user.id, None) is not None:
        await message.answer("❌ Отменено. Сообщение не отправлено.")
    else:
        await message.answer("Нечего отменять.")


# ============================================================
# Catch-all для ввода сообщения
# ============================================================
@router.message(F.text & ~F.text.startswith("/"), _is_waiting_chat_reply)
async def handle_chat_reply(message: Message):
    chat_id = PENDING_CHAT_REPLY.pop(message.from_user.id, None)
    if chat_id is None:
        return

    text = message.text.strip()
    if not text:
        await message.answer("Пустое сообщение. Попробуй ещё раз.")
        return

    result = await send_chat_message(
        bot=message.bot,
        sender_telegram_id=message.from_user.id,
        chat_id=chat_id,
        text=text[:1000],
        msg_type="text",
    )

    if result:
        await track("chat_message_sent", telegram_id=message.from_user.id, payload={"chat_id": chat_id})
        await message.answer(
            "✅ Сообщение отправлено.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="📜 Открыть чат", callback_data=f"chat_open_{chat_id}")],
                ]
            ),
        )
    else:
        await message.answer("❌ Не удалось отправить. Возможно, собеседник отключил сообщения.")


# ============================================================
# Универсальная отправка
# ============================================================
async def _reply(message_or_callback, text: str, kb) -> None:
    if isinstance(message_or_callback, CallbackQuery):
        try:
            await message_or_callback.message.edit_text(text, reply_markup=kb)
        except Exception:
            await message_or_callback.message.answer(text, reply_markup=kb)
    else:
        await message_or_callback.answer(text, reply_markup=kb)