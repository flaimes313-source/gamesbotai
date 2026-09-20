"""
Раз в неделю публикует топы игроков.
"""
import asyncio
from datetime import datetime, timedelta, timezone

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError
from sqlalchemy import select

from database.connection import async_session
from database.models import Profile, User, UserEngagement
from services.analytics.tracker import track
from services.engagement.points import title_for_level
from utils.logging import get_logger

logger = get_logger(__name__)


# Воскресенье, 20:00 UTC
TOPS_WEEKDAY = 6
TOPS_HOUR_UTC = 20

# Не спамить чаще, чем раз в 7 дней
MIN_INTERVAL_DAYS = 6


async def send_weekly_tops(bot: Bot) -> None:
    """
    Раз в неделю рассылает топы активным игрокам.
    """
    async with async_session() as session:
        # Проверяем, когда последний раз отправляли
        from database.models import Event
        from sqlalchemy import func

        last_event = (await session.execute(
            select(Event.created_at)
            .where(Event.name == "tops_sent")
            .order_by(Event.id.desc())
            .limit(1)
        )).scalar_one_or_none()

        if last_event:
            now = datetime.now(timezone.utc)
            # Учитываем tz
            if last_event.tzinfo is None:
                last_event = last_event.replace(tzinfo=timezone.utc)
            if (now - last_event) < timedelta(days=MIN_INTERVAL_DAYS):
                logger.info("[TOPS] Skipped — sent recently")
                return

        # Получаем активных игроков в игре
        users = (await session.execute(
            select(User)
            .where(User.is_blocked.is_(False))
            .where(User.participates_in_game.is_(True))
            .where(User.last_active_at >= datetime.now(timezone.utc) - timedelta(days=14))
        )).scalars().all()

    if not users:
        logger.info("[TOPS] No active users")
        return

    # Строим тексты топов
    tops_text = await _build_all_tops()

    if not tops_text:
        logger.info("[TOPS] No data")
        return

    sent = 0
    for user in users:
        try:
            await bot.send_message(
                user.telegram_id,
                tops_text,
            )
            sent += 1
            await asyncio.sleep(0.05)
        except TelegramForbiddenError:
            pass
        except Exception:
            logger.exception(f"[TOPS] Failed for {user.telegram_id}")

    await track("tops_sent", telegram_id=0, payload={"sent": sent})
    logger.info(f"[TOPS] Sent to {sent} users")


async def _build_all_tops() -> str:
    """Строит общий текст со всеми топами."""
    lines = ["🏆 <b>НЕДЕЛЬНЫЕ ТОПЫ</b>\n"]

    # Топ по хаосу
    async with async_session() as session:
        rows = (await session.execute(
            select(Profile, User)
            .join(User, User.id == Profile.user_id)
            .where(User.is_blocked.is_(False))
            .where(User.participates_in_game.is_(True))
            .order_by(Profile.chaos.desc())
            .limit(5)
        )).all()

    if rows:
        lines.append("🔥 <b>По хаосу:</b>")
        for i, (p, u) in enumerate(rows, 1):
            name = u.first_name or "Игрок"
            lines.append(f"  {i}. {name} — {p.chaos}")
        lines.append("")

    # Топ по юмору
    async with async_session() as session:
        rows = (await session.execute(
            select(Profile, User)
            .join(User, User.id == Profile.user_id)
            .where(User.is_blocked.is_(False))
            .where(User.participates_in_game.is_(True))
            .order_by(Profile.humor.desc())
            .limit(5)
        )).all()

    if rows:
        lines.append("😂 <b>По юмору:</b>")
        for i, (p, u) in enumerate(rows, 1):
            name = u.first_name or "Игрок"
            lines.append(f"  {i}. {name} — {p.humor}")
        lines.append("")

    # Топ по очкам
    async with async_session() as session:
        rows = (await session.execute(
            select(UserEngagement, User)
            .join(User, User.id == UserEngagement.user_id)
            .where(User.is_blocked.is_(False))
            .order_by(UserEngagement.total_points.desc())
            .limit(5)
        )).all()

    if rows:
        lines.append("⭐ <b>По очкам:</b>")
        for i, (e, u) in enumerate(rows, 1):
            name = u.first_name or "Игрок"
            title = title_for_level(e.level)
            lines.append(f"  {i}. {name} — {e.total_points} ({title})")
        lines.append("")

    lines.append("🎯 Проверь свой прогресс: «📊 Моя статистика»")

    return "\n".join(lines)


async def tops_loop(bot: Bot) -> None:
    """
    Фоновый цикл: раз в час проверяет — не пора ли отправить топы.
    Отправляет в воскресенье в 20:00 UTC.
    """
    # Первый запуск через 10 минут после старта
    await asyncio.sleep(600)

    while True:
        try:
            now = datetime.now(timezone.utc)
            if now.weekday() == TOPS_WEEKDAY and now.hour == TOPS_HOUR_UTC:
                await send_weekly_tops(bot)
        except Exception:
            logger.exception("[TOPS] Loop iteration failed")

        # Проверяем каждый час
        await asyncio.sleep(3600)