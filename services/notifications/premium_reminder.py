import asyncio
from datetime import datetime, timedelta, timezone

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select

from database.connection import async_session
from database.models import User
from services.analytics.tracker import track
from services.timezones import is_night_now
from utils.logging import get_logger

logger = get_logger(__name__)


PRO_DAYS = 30
PRO_PRICE = 390

# За сколько дней напоминать
REMIND_DAYS = (3, 1)


async def send_premium_reminders(bot: Bot) -> None:
    """
    Раз в сутки:
    - за 3 и 1 день до окончания PRO → напоминание
    - в день окончания → «PRO закончилось»
    """
    now = datetime.now(timezone.utc)

    async with async_session() as session:
        users = (await session.execute(
            select(User)
            .where(User.premium_until.isnot(None))
            .where(User.is_blocked.is_(False))
        )).scalars().all()

    sent_expiring = 0
    sent_expired = 0

    for user in users:
        if user.premium_until is None:
            continue

        # Не беспокоим ночью
        try:
            if is_night_now(user.timezone):
                continue
        except Exception:
            pass

        # Разница в днях между окончанием и сейчас
        delta = user.premium_until - now
        days_left = delta.days

        # ==== Уже истекло? ====
        if delta.total_seconds() <= 0:
            # Отправляем ОДИН раз — проверяем событие
            if await _was_sent_recently(user.telegram_id, "premium_expired", hours=48):
                continue
            try:
                await _send_expired(bot, user)
                await track(
                    "premium_expired",
                    telegram_id=user.telegram_id,
                    payload={"premium_until": user.premium_until.isoformat()},
                )
                sent_expired += 1
                await asyncio.sleep(0.05)
            except TelegramForbiddenError:
                pass
            except Exception:
                logger.exception(f"Failed to send expired to {user.telegram_id}")
            continue

        # ==== За 3 и 1 день ====
        if days_left in REMIND_DAYS:
            event_name = f"premium_reminder_{days_left}d"
            if await _was_sent_recently(user.telegram_id, event_name, hours=23):
                continue
            try:
                await _send_expiring(bot, user, days_left)
                await track(
                    event_name,
                    telegram_id=user.telegram_id,
                    payload={"days_left": days_left},
                )
                sent_expiring += 1
                await asyncio.sleep(0.05)
            except TelegramForbiddenError:
                pass
            except Exception:
                logger.exception(f"Failed to send reminder to {user.telegram_id}")

    logger.info(
        f"Premium reminders: expiring={sent_expiring}, expired={sent_expired}"
    )


async def _was_sent_recently(telegram_id: int, event_name: str, hours: int = 23) -> bool:
    """Проверяет, отправляли ли уже это уведомление за последние N часов."""
    from sqlalchemy import func
    from database.models import Event

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
# Напоминание за 3 и 1 день
# ============================================================
async def _send_expiring(bot: Bot, user: User, days_left: int) -> None:
    if days_left == 3:
        emoji = "⏰"
        when = "через 3 дня"
        title = "PRO истекает через 3 дня"
    else:
        emoji = "🚨"
        when = "завтра"
        title = "PRO истекает завтра"

    until_str = user.premium_until.strftime("%d.%m.%Y")

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

    await bot.send_message(user.telegram_id, text, reply_markup=kb)


# ============================================================
# PRO закончилось
# ============================================================
async def _send_expired(bot: Bot, user: User) -> None:
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

    await bot.send_message(user.telegram_id, text, reply_markup=kb)


# ============================================================
# Фоновый цикл
# ============================================================
async def premium_reminder_loop(bot: Bot) -> None:
    """Раз в 6 часов проверяет и рассылает напоминания."""
    # Первый запуск через 5 минут после старта
    await asyncio.sleep(300)

    while True:
        try:
            await send_premium_reminders(bot)
        except Exception:
            logger.exception("Premium reminder loop iteration failed")

        await asyncio.sleep(6 * 3600)