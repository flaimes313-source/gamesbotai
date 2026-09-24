"""
Напоминания о PRO — через hub (Этап 4).

Три типа:
1. premium_reminder_3d — за 3 дня до окончания PRO.
2. premium_reminder_1d — за 1 день до окончания.
3. premium_expired — в день окончания (или после).

Hub сам проверит:
- feature flag premium_reminder_enabled,
- настройки юзера (premium_reminder_enabled),
- тихие часы,
- дневной лимит,
- дубли.

Cooldown (23ч для 3d/1d, 48ч для expired) — оставляем свой (правило фичи).
"""

import asyncio
from datetime import datetime, timedelta, timezone

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import func, select

from database.connection import async_session
from database.models import Event, User
from services.notifications.hub import schedule_notification
from utils.logging import get_logger

logger = get_logger(__name__)


# ============================================================
# НАСТРОЙКИ
# ============================================================
PRO_DAYS = 30
PRO_PRICE = 390
REMIND_DAYS = (3, 1)
CHECK_INTERVAL_SECONDS = 6 * 3600
INITIAL_DELAY_SECONDS = 300


# ============================================================
# ХЕЛПЕР: cooldown проверка
# ============================================================
async def _was_sent_recently(
    telegram_id: int,
    event_name: str,
    hours: int = 23,
) -> bool:
    """Проверяет, отправляли ли уже это уведомление за последние N часов."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

    async with async_session() as session:
        cnt = (await session.execute(
            select(func.count(Event.id))
            .where(Event.name == event_name)
            .where(Event.telegram_id == telegram_id)
            .where(Event.created_at >= cutoff)
        )).scalar_one()

    return cnt > 0


# ============================================================
# ФОРМИРОВАНИЕ PAYLOAD
# ============================================================
def _build_expiring_payload(
    days_left: int,
    until_str: str,
) -> dict:
    """Payload для premium_reminder_3d / premium_reminder_1d."""
    if days_left == 3:
        emoji = "⏰"
        when = "через 3 дня"
        title = "PRO истекает через 3 дня"
    else:
        emoji = "🚨"
        when = "завтра"
        title = "PRO истекает завтра"

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text=f"💎 Продлить PRO ({int(PRO_PRICE)} ₽)",
                callback_data="buy_pro",
            )],
        ]
    )

    text = (
        f"{emoji} <b>{title}</b>\n\n"
        f"Твоя PRO подписка заканчивается <b>{when}</b> "
        f"({until_str}).\n\n"
        f"После окончания ты потеряешь:\n"
        f"• ♾ Безлимитные AI-анализы\n"
        f"• 🚀 Расширенные режимы поиска\n"
        f"• 🤖 AI-помощник в чатах\n"
        f"• 🚫 Отсутствие рекламы\n\n"
        f"Продли сейчас, чтобы ничего не потерять 👇"
    )

    return {"text": text, "reply_markup": kb}


def _build_expired_payload() -> dict:
    """Payload для premium_expired."""
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text=f"💎 Возобновить PRO ({int(PRO_PRICE)} ₽)",
                callback_data="buy_pro",
            )],
        ]
    )

    text = (
        "😢 <b>PRO закончилось</b>\n\n"
        "Ты вернулся на обычный режим:\n"
        "• 5 AI-анализов в день (было 50)\n"
        "• Ограниченные режимы поиска\n"
        "• Без AI-помощника в чатах\n"
        "• Реклама вернулась\n\n"
        "Хочешь вернуть максимум? Подключи PRO снова 👇"
    )

    return {"text": text, "reply_markup": kb}


# ============================================================
# ГЛАВНАЯ ФУНКЦИЯ
# ============================================================
async def send_premium_reminders(bot: Bot) -> None:
    """
    Проходит по юзерам с активным PRO, ставит в hub напоминания.
    """
    now = datetime.now(timezone.utc)

    async with async_session() as session:
        users = (await session.execute(
            select(User)
            .where(User.premium_until.isnot(None))
            .where(User.is_blocked.is_(False))
        )).scalars().all()

    scheduled = 0

    for user in users:
        if user.premium_until is None:
            continue

        # Сохраняем до выхода из сессии
        user_id = user.id
        user_tz = user.timezone
        telegram_id = user.telegram_id
        premium_until = user.premium_until

        # Приводим к aware
        if premium_until.tzinfo is None:
            premium_until = premium_until.replace(tzinfo=timezone.utc)

        delta = premium_until - now
        days_left = delta.days

        # ==== 1. Уже истекло ====
        if delta.total_seconds() <= 0:
            if await _was_sent_recently(telegram_id, "premium_expired", hours=48):
                continue

            payload = _build_expired_payload()
            ok = await schedule_notification(
                user_id=user_id,
                kind="premium_expired",
                priority=1,   # очень высокий — игнорим дневной лимит
                payload=payload,
                tz_name=user_tz,
            )
            if ok:
                scheduled += 1
            continue

        # ==== 2. За 3 и 1 день ====
        if days_left in REMIND_DAYS:
            event_name = f"premium_reminder_{days_left}d"
            if await _was_sent_recently(telegram_id, event_name, hours=23):
                continue

            until_str = premium_until.strftime("%d.%m.%Y")
            payload = _build_expiring_payload(days_left, until_str)

            ok = await schedule_notification(
                user_id=user_id,
                kind=event_name,
                priority=1,   # очень высокий — игнорим дневной лимит
                payload=payload,
                tz_name=user_tz,
            )
            if ok:
                scheduled += 1

    if scheduled:
        logger.info(f"[PREMIUM_REMINDER] scheduled={scheduled}")


# ============================================================
# ЦИКЛ
# ============================================================
async def premium_reminder_loop(bot: Bot) -> None:
    """Раз в 6 часов проверяет и рассылает напоминания."""
    await asyncio.sleep(INITIAL_DELAY_SECONDS)

    while True:
        try:
            await send_premium_reminders(bot)
        except Exception:
            logger.exception("[PREMIUM_REMINDER] loop iteration failed")

        await asyncio.sleep(CHECK_INTERVAL_SECONDS)