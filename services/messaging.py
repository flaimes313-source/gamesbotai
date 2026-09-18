from aiogram import Bot
from sqlalchemy import select

from database.connection import async_session
from database.models import Message, User
from utils.logging import get_logger

logger = get_logger(__name__)


async def deliver_message(
    bot: Bot,
    sender_telegram_id: int,
    receiver_user_id: int,
    text: str,
    msg_type: str = "text",
) -> bool:
    """
    Сохраняет сообщение в БД и уведомляет получателя через бота.
    Возвращает True при успешной отправке уведомления.

    Доставка односторонняя: получатель видит сообщение и username отправителя,
    чтобы при желании написать ему в Telegram напрямую.
    """
    async with async_session() as session:
        sender = (
            await session.execute(
                select(User).where(User.telegram_id == sender_telegram_id)
            )
        ).scalar_one_or_none()
        receiver = (
            await session.execute(
                select(User).where(User.id == receiver_user_id)
            )
        ).scalar_one_or_none()

        if sender is None or receiver is None:
            logger.warning(
                f"deliver_message: sender or receiver not found "
                f"(sender_tg={sender_telegram_id}, receiver_id={receiver_user_id})"
            )
            return False

        if not receiver.allow_messages:
            logger.info(f"Receiver {receiver.id} disallows messages")
            return False

        msg = Message(
            sender_id=sender.id,
            receiver_id=receiver.id,
            type=msg_type,
            text=text,
            status="sent",
        )
        session.add(msg)
        await session.commit()
        sender_id = sender.id

    # --------------------------------------------------------
    # Формируем уведомление получателю
    # --------------------------------------------------------
    sender_name = sender.first_name or "Игрок"
    sender_handle = f"@{sender.username}" if sender.username else None

    if msg_type == "joke":
        prefix = "😂 <b>Прикол от игрока</b>"
    else:
        prefix = "💌 <b>Новое сообщение от игрока</b>"

    header = f"{prefix}\n\n👤 {sender_name}"
    if sender_handle:
        header += f" · {sender_handle}"

    # Подсказка про ответ — с кликабельным username
    if sender_handle:
        footer = (
            f"\n\n💬 Хочешь ответить? Напиши в Telegram напрямую: {sender_handle}"
        )
    else:
        footer = (
            "\n\n💬 Ответить в Telegram нельзя — игрок скрыл свой username."
        )

    notification = (
        f"{header}\n\n"
        f"<i>{text}</i>"
        f"{footer}"
    )

    try:
        await bot.send_message(receiver.telegram_id, notification)
        logger.info(f"Message delivered: {sender_id} → {receiver.id}")
        return True
    except Exception as e:
        logger.exception(f"Failed to deliver message: {e}")
        return False


async def get_inbox(telegram_id: int, limit: int = 10) -> list[dict]:
    """Последние входящие сообщения пользователя."""
    async with async_session() as session:
        me = (
            await session.execute(
                select(User).where(User.telegram_id == telegram_id)
            )
        ).scalar_one_or_none()
        if me is None:
            return []

        rows = (
            await session.execute(
                select(Message, User)
                .join(User, User.id == Message.sender_id)
                .where(Message.receiver_id == me.id)
                .order_by(Message.id.desc())
                .limit(limit)
            )
        ).all()

    return [
        {
            "sender_name": u.first_name or "Игрок",
            "sender_username": u.username,
            "text": m.text,
            "type": m.type,
            "created_at": m.created_at,
        }
        for m, u in rows
    ]