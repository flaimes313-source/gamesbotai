from datetime import datetime
from typing import Optional

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import or_, select, update

from database.connection import async_session
from database.models import Chat, Message, User
from utils.logging import get_logger

logger = get_logger(__name__)


# ============================================================
# Получение / создание чата
# ============================================================
async def get_or_create_chat(session, user_a_id: int, user_b_id: int) -> Chat:
    """
    Возвращает существующий чат между двумя пользователями
    или создаёт новый.

    user1_id всегда < user2_id — чтобы пара (A, B) и (B, A)
    давала одну и ту же запись (уникальный индекс uq_chat_pair).
    """
    u1, u2 = (user_a_id, user_b_id) if user_a_id < user_b_id else (user_b_id, user_a_id)

    chat = (await session.execute(
        select(Chat).where(Chat.user1_id == u1, Chat.user2_id == u2)
    )).scalar_one_or_none()

    if chat is None:
        chat = Chat(user1_id=u1, user2_id=u2)
        session.add(chat)
        await session.commit()
        await session.refresh(chat)
        logger.info(f"Chat created: {u1} <-> {u2}")

    return chat


# ============================================================
# Список чатов пользователя
# ============================================================
async def list_user_chats(session, user_id: int, limit: int = 20) -> list[dict]:
    """
    Возвращает список диалогов пользователя:
    - собеседник
    - последнее сообщение
    - количество непрочитанных
    """
    chats = (await session.execute(
        select(Chat)
        .where(or_(Chat.user1_id == user_id, Chat.user2_id == user_id))
        .order_by(Chat.updated_at.desc())
        .limit(limit)
    )).scalars().all()

    result: list[dict] = []
    for chat in chats:
        other_id = chat.user2_id if chat.user1_id == user_id else chat.user1_id

        other = (await session.execute(
            select(User).where(User.id == other_id)
        )).scalar_one_or_none()
        if other is None:
            continue

        last_msg = (await session.execute(
            select(Message)
            .where(Message.chat_id == chat.id)
            .order_by(Message.id.desc())
            .limit(1)
        )).scalar_one_or_none()

        # Непрочитанные — только от собеседника
        unread_rows = (await session.execute(
            select(Message.id)
            .where(Message.chat_id == chat.id)
            .where(Message.sender_id == other_id)
            .where(Message.is_read.is_(False))
        )).scalars().all()

        result.append({
            "chat_id": chat.id,
            "other_id": other.id,
            "other_name": other.first_name or "Игрок",
            "other_username": other.username,
            "show_username": other.show_username,
            "allow_messages": other.allow_messages,
            "last_text": (last_msg.text or "")[:100] if last_msg else "",
            "last_type": last_msg.type if last_msg else "text",
            "last_from_me": (last_msg.sender_id == user_id) if last_msg else False,
            "unread_count": len(unread_rows),
            "updated_at": chat.updated_at,
        })

    return result


# ============================================================
# История сообщений чата
# ============================================================
async def get_chat_messages(session, chat_id: int, limit: int = 30) -> list[Message]:
    """
    Возвращает последние N сообщений чата в порядке от старых к новым
    (то есть как в мессенджере — сверху старые, снизу новые).
    """
    messages = (await session.execute(
        select(Message)
        .where(Message.chat_id == chat_id)
        .order_by(Message.id.desc())
        .limit(limit)
    )).scalars().all()

    return list(reversed(messages))


# ============================================================
# Отметка "прочитано"
# ============================================================
async def mark_chat_read(session, chat: Chat, user_id: int) -> None:
    """Отмечает все входящие сообщения в чате как прочитанные для user_id."""
    await session.execute(
        update(Message)
        .where(Message.chat_id == chat.id)
        .where(Message.receiver_id == user_id)
        .where(Message.is_read.is_(False))
        .values(is_read=True)
    )
    await session.commit()


# ============================================================
# Отправка сообщения в чат
# ============================================================
async def send_chat_message(
    bot: Bot,
    sender_telegram_id: int,
    chat_id: int,
    text: str,
    msg_type: str = "text",
) -> Optional[Message]:
    """
    Сохраняет сообщение в чате и уведомляет получателя через бота.

    Возвращает созданное Message или None, если что-то пошло не так.
    """
    async with async_session() as session:
        sender = (await session.execute(
            select(User).where(User.telegram_id == sender_telegram_id)
        )).scalar_one_or_none()
        if sender is None:
            logger.warning(f"send_chat_message: sender not found ({sender_telegram_id})")
            return None

        chat = (await session.execute(
            select(Chat).where(Chat.id == chat_id)
        )).scalar_one_or_none()
        if chat is None:
            logger.warning(f"send_chat_message: chat not found ({chat_id})")
            return None

        # Определяем получателя
        if chat.user1_id == sender.id:
            receiver_id = chat.user2_id
        elif chat.user2_id == sender.id:
            receiver_id = chat.user1_id
        else:
            logger.warning(f"send_chat_message: sender {sender.id} not in chat {chat_id}")
            return None

        receiver = (await session.execute(
            select(User).where(User.id == receiver_id)
        )).scalar_one_or_none()
        if receiver is None:
            return None

        if not receiver.allow_messages:
            logger.info(f"Receiver {receiver.id} disallows messages")
            return None

        msg = Message(
            chat_id=chat.id,
            sender_id=sender.id,
            receiver_id=receiver.id,
            type=msg_type,
            text=text,
            status="sent",
            is_read=False,
        )
        session.add(msg)

        # Обновляем updated_at чата — чтобы в списке чатов он поднимался вверх
        chat.updated_at = datetime.utcnow()

        await session.commit()
        await session.refresh(msg)

        sender_name = sender.first_name or "Игрок"
        sender_username = sender.username
        receiver_telegram_id = receiver.telegram_id
        receiver_user_id = receiver.id
        sender_id = sender.id
        message_id = msg.id

    # --------------------------------------------------------
    # Уведомление получателю
    # --------------------------------------------------------
    telegram_hint = (
        f"\n\n👤 Открыть в Telegram: @{sender_username}"
        if sender_username
        else ""
    )

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="💬 Ответить в боте",
                callback_data=f"chat_reply_{chat_id}",
            )],
            [InlineKeyboardButton(
                text="📜 Открыть чат",
                callback_data=f"chat_open_{chat_id}",
            )],
        ]
    )

    notification = (
        f"💬 <b>Новое сообщение в чате</b>\n\n"
        f"👤 <b>{sender_name}</b>\n\n"
        f"<i>{text}</i>"
        f"{telegram_hint}"
    )

    try:
        await bot.send_message(receiver_telegram_id, notification, reply_markup=kb)
        logger.info(f"Chat message delivered: {sender_id} → {receiver_user_id} (chat {chat_id}, msg {message_id})")
    except Exception:
        logger.exception("Failed to deliver chat notification")

    return msg