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
from database.models import Chat, User
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
# Клавиатуры
# ============================================================
def chat_list_back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🏠 В главное меню", callback_data="back_to_main")],
        ]
    )


def chat_actions_kb(chat_id: int, other_username: str | None = None) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(
            text="✍️ Ответить",
            callback_data=f"chat_reply_{chat_id}",
        )],
        [InlineKeyboardButton(
            text="🔄 Обновить",
            callback_data=f"chat_open_{chat_id}",
        )],
    ]
    if other_username:
        rows.append([InlineKeyboardButton(
            text=f"👤 @{other_username} в Telegram",
            url=f"https://t.me/{other_username}",
        )])
    rows.append([InlineKeyboardButton(
        text="⬅️ К списку чатов",
        callback_data="chat_list",
    )])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def chat_list_item_kb(chat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="💬 Открыть чат",
                callback_data=f"chat_open_{chat_id}",
            )],
        ]
    )


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
            text = "Сначала отправь фото — создай профиль!"
            return await _reply(message_or_callback, text, None)

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

    # Каждая строка — отдельная кнопка «Открыть чат»
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

        # Проверка доступа
        if me.id not in (chat.user1_id, chat.user2_id):
            return await _reply(message_or_callback, "Нет доступа к чату.", None)

        other_id = chat.user2_id if chat.user1_id == me.id else chat.user1_id
        other = (await session.execute(
            select(User).where(User.id == other_id)
        )).scalar_one_or_none()
        if other is None:
            return await _reply(message_or_callback, "Собеседник не найден.", None)

        messages = await get_chat_messages(session, chat.id, limit=30)

        # Отмечаем прочитанным
        await mark_chat_read(session, chat, me.id)

    # Формируем заголовок
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

    # Если длинный — обрезаем
    if len(text) > 3500:
        text = text[:3500] + "\n\n<i>…<br/>История обрезана</i>"

    kb = chat_actions_kb(chat.id, other_username)

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
        await message.answer(
            "❌ Не удалось отправить. Возможно, собеседник отключил сообщения."
        )


# ============================================================
# Универсальная отправка ответа
# ============================================================
async def _reply(message_or_callback, text: str, kb) -> None:
    if isinstance(message_or_callback, CallbackQuery):
        try:
            await message_or_callback.message.edit_text(text, reply_markup=kb)
        except Exception:
            await message_or_callback.message.answer(text, reply_markup=kb)
    else:
        await message_or_callback.answer(text, reply_markup=kb)