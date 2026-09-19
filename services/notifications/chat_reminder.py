import asyncio
from datetime import datetime, timedelta, timezone

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import func, select

from database.connection import async_session
from database.models import Chat, Event, Message, User
from services.analytics.tracker import track
from services.timezones import is_night_now
from utils.logging import get_logger

logger = get_logger(__name__)

REMINDER_AFTER_HOURS = 24
REMINDER_COOLDOWN_HOURS = 48


async def send_chat_reminders(bot: Bot) -> None:
    """
    Находит пользователей, которым не ответили 24+ часа,
    и отправляет напоминание. Не спамит чаще, чем раз в 48 часов.

    ⚠️ Не отправляет ночью по локальному времени юзера.
    """
    now = datetime.now(timezone.utc)  # ⚠️ aware UTC
    cutoff = now - timedelta(hours=REMINDER_AFTER_HOURS)
    cooldown_cutoff = now - timedelta(hours=REMINDER_COOLDOWN_HOURS)

    async with async_session() as session:
        chats = (await session.execute(select(Chat))).scalars().all()

    reminders_sent = 0

    for chat in chats:
        for me_id, other_id in [(chat.user1_id, chat.user2_id), (chat.user2_id, chat.user1_id)]:
            async with async_session() as session:
                last_msg = (await session.execute(
                    select(Message)
                    .where(Message.chat_id == chat.id)
                    .order_by(Message.id.desc())
                    .limit(1)
                )).scalar_one_or_none()

                if last_msg is None:
                    continue

                # Сообщение должно быть мне
                if last_msg.receiver_id != me_id:
                    continue

                # Свежее — рано напоминать
                if last_msg.created_at > cutoff:
                    continue

                me = (await session.execute(
                    select(User).where(User.id == me_id)
                )).scalar_one_or_none()
                if me is None or me.is_blocked:
                    continue

                # ⚠️ Не беспокоим ночью
                if is_night_now(me.timezone):
                    continue

                # Есть ли мой ответ после этого сообщения
                reply_after = (await session.execute(
                    select(func.count(Message.id))
                    .where(Message.chat_id == chat.id)
                    .where(Message.sender_id == me_id)
                    .where(Message.id > last_msg.id)
                )).scalar_one()
                if reply_after > 0:
                    continue

                # Cooldown: уже отправляли напоминание недавно?
                recent_reminder = (await session.execute(
                    select(func.count(Event.id))
                    .where(Event.name == "chat_reminder_sent")
                    .where(Event.telegram_id == me.telegram_id)
                    .where(Event.created_at >= cooldown_cutoff)
                )).scalar_one()
                if recent_reminder > 0:
                    continue

                other = (await session.execute(
                    select(User).where(User.id == other_id)
                )).scalar_one_or_none()
                other_name = (other.first_name if other else None) or "Собеседник"
                receiver_telegram_id = me.telegram_id

            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(
                        text="💬 Открыть чат",
                        callback_data=f"chat_open_{chat.id}",
                    )],
                ]
            )

            try:
                await bot.send_message(
                    receiver_telegram_id,
                    f"⏰ <b>Тебе не ответили в чате</b>\n\n"
                    f"👤 {other_name} пока не ответил(а).\n"
                    f"Хочешь напомнить о себе или продолжить диалог?",
                    reply_markup=kb,
                )
                await track(
                    "chat_reminder_sent",
                    telegram_id=receiver_telegram_id,
                    payload={"chat_id": chat.id},
                )
                reminders_sent += 1
                await asyncio.sleep(0.05)
            except TelegramForbiddenError:
                pass
            except Exception:
                logger.exception(f"Failed to send reminder to {receiver_telegram_id}")

    logger.info(f"Chat reminders sent: {reminders_sent}")


async def chat_reminder_loop(bot: Bot) -> None:
    """Фоновый цикл: раз в 6 часов."""
    while True:
        try:
            await send_chat_reminders(bot)
        except Exception:
            logger.exception("Chat reminder loop iteration failed")

        await asyncio.sleep(6 * 3600)