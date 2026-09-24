"""
Напоминание о непрочитанных в чате — через hub (Этап 4).

Логика:
- Раз в 6 часов проходим по всем чатам.
- Ищем: где мне (получателю) не ответили 24+ часа.
- Исключаем: свежие сообщения, уже отвеченные, заблокированных, cooldown 48ч.
- Ставим в hub (kind="chat_reminder", priority=3).

Hub сам проверит:
- feature flag chat_reminder_enabled,
- настройки юзера (chat_reminder_enabled),
- тихие часы,
- дневной лимит,
- дубли (chat_reminder_sent сегодня?).

Cooldown 48ч — оставляем свой (это правило фичи, не дубликат).
"""

import asyncio
from datetime import datetime, timedelta, timezone

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import func, select

from database.connection import async_session
from database.models import Chat, Event, Message, User
from services.notifications.hub import schedule_notification
from utils.logging import get_logger

logger = get_logger(__name__)


# ============================================================
# НАСТРОЙКИ
# ============================================================
REMINDER_AFTER_HOURS = 24       # не ответили больше суток
REMINDER_COOLDOWN_HOURS = 48    # не спамить чаще раза в 2 дня
CHECK_INTERVAL_SECONDS = 6 * 3600
REMINDER_PRIORITY = 3


# ============================================================
# ОСНОВНАЯ ФУНКЦИЯ
# ============================================================
async def send_chat_reminders(bot: Bot) -> None:
    """
    Проходит по чатам, ставит в hub напоминания.
    """
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=REMINDER_AFTER_HOURS)
    cooldown_cutoff = now - timedelta(hours=REMINDER_COOLDOWN_HOURS)

    async with async_session() as session:
        chats = (await session.execute(select(Chat))).scalars().all()

    scheduled = 0

    for chat in chats:
        for me_id, other_id in [(chat.user1_id, chat.user2_id), (chat.user2_id, chat.user1_id)]:
            async with async_session() as session:
                # Последнее сообщение в чате
                last_msg = (await session.execute(
                    select(Message)
                    .where(Message.chat_id == chat.id)
                    .order_by(Message.id.desc())
                    .limit(1)
                )).scalar_one_or_none()

                if last_msg is None:
                    continue

                # Должно быть мне
                if last_msg.receiver_id != me_id:
                    continue

                # Свежее — рано напоминать
                if last_msg.created_at > cutoff:
                    continue

                # Получатель напоминания
                me = (await session.execute(
                    select(User).where(User.id == me_id)
                )).scalar_one_or_none()
                if me is None or me.is_blocked:
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

                # Cooldown 48ч (своё правило фичи)
                recent_reminder = (await session.execute(
                    select(func.count(Event.id))
                    .where(Event.name == "chat_reminder_sent")
                    .where(Event.telegram_id == me.telegram_id)
                    .where(Event.created_at >= cooldown_cutoff)
                )).scalar_one()
                if recent_reminder > 0:
                    continue

                # Имя собеседника
                other = (await session.execute(
                    select(User).where(User.id == other_id)
                )).scalar_one_or_none()
                other_name = (other.first_name if other else None) or "Собеседник"

                # Идентификаторы для передачи
                me_user_id = me.id
                me_tz = me.timezone
                chat_id = chat.id

            # Клавиатура
            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(
                        text="💬 Открыть чат",
                        callback_data=f"chat_open_{chat_id}",
                    )],
                ]
            )

            # Текст
            text = (
                f"⏰ <b>Тебе не ответили в чате</b>\n\n"
                f"👤 {other_name} пока не ответил(а).\n"
                f"Хочешь напомнить о себе или продолжить диалог?"
            )

            # Ставим в hub
            ok = await schedule_notification(
                user_id=me_user_id,
                kind="chat_reminder",
                priority=REMINDER_PRIORITY,
                payload={
                    "text": text,
                    "reply_markup": kb,
                },
                tz_name=me_tz,
            )
            if ok:
                scheduled += 1

    if scheduled:
        logger.info(f"[CHAT_REMINDER] scheduled={scheduled}")


# ============================================================
# ЦИКЛ
# ============================================================
async def chat_reminder_loop(bot: Bot) -> None:
    """Фоновый цикл: раз в 6 часов."""
    while True:
        try:
            await send_chat_reminders(bot)
        except Exception:
            logger.exception("[CHAT_REMINDER] loop iteration failed")

        await asyncio.sleep(CHECK_INTERVAL_SECONDS)