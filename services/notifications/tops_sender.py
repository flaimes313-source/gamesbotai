"""
Недельные топы — через hub (Этап 4).

Логика:
- Раз в час проверяем: сейчас вс 20:00 UTC?
- Проверяем: не слали ли глобально топы за последние 6 дней?
- Строим общий текст топов (по хаосу, юмору, очкам).
- Ставим в hub для каждого активного юзера (kind="tops", priority=4).

Hub сам проверит:
- feature flag tops_enabled,
- настройки юзера (tops_enabled),
- тихие часы (по TZ юзера),
- дневной лимит (2 проактивных),
- дубли (tops_sent сегодня?).

Приоритет 4 — низкий. Если лимит набран, топы отбрасываются.
"""

import asyncio
from datetime import datetime, timedelta, timezone

from aiogram import Bot
from sqlalchemy import func, select

from database.connection import async_session
from database.models import Event, Profile, User, UserEngagement
from services.engagement.points import title_for_level
from services.notifications.hub import schedule_notification
from utils.logging import get_logger

logger = get_logger(__name__)


# ============================================================
# НАСТРОЙКИ
# ============================================================
TOPS_WEEKDAY = 6                # 6 = воскресенье (0=пн)
TOPS_HOUR_UTC = 20
MIN_INTERVAL_DAYS = 6
CHECK_INTERVAL_SECONDS = 3600   # каждый час
INITIAL_DELAY_SECONDS = 600
TOPS_PRIORITY = 4               # низкий


# ============================================================
# ГЛОБАЛЬНЫЙ COOLDOWN
# ============================================================
async def _tops_sent_recently() -> bool:
    """
    Проверяет, отправлялись ли топы за последние MIN_INTERVAL_DAYS дней.
    Глобально — по любому юзеру.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=MIN_INTERVAL_DAYS)

    try:
        async with async_session() as session:
            cnt = (await session.execute(
                select(func.count(Event.id))
                .where(Event.name == "tops_sent")
                .where(Event.created_at >= cutoff)
            )).scalar_one()
            return cnt > 0
    except Exception:
        logger.exception("[TOPS] cooldown check failed")
        return False


# ============================================================
# СБОР ТЕКСТА
# ============================================================
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


# ============================================================
# ОТПРАВКА
# ============================================================
async def send_weekly_tops(bot: Bot) -> None:
    """
    Ставит топы в hub для активных юзеров.
    """
    # Глобальный cooldown
    if await _tops_sent_recently():
        logger.info("[TOPS] skipped — sent recently")
        return

    # Активные юзеры в игре
    cutoff = datetime.now(timezone.utc) - timedelta(days=14)
    async with async_session() as session:
        users = (await session.execute(
            select(User)
            .where(User.is_blocked.is_(False))
            .where(User.participates_in_game.is_(True))
            .where(User.last_active_at >= cutoff)
        )).scalars().all()

    if not users:
        logger.info("[TOPS] no active users")
        return

    # Строим текст
    tops_text = await _build_all_tops()
    if not tops_text:
        logger.info("[TOPS] no data")
        return

    # Ставим в hub для каждого
    scheduled = 0
    for user in users:
        try:
            ok = await schedule_notification(
                user_id=user.id,
                kind="tops",
                priority=TOPS_PRIORITY,
                payload={"text": tops_text},
                tz_name=user.timezone,
            )
            if ok:
                scheduled += 1
        except Exception:
            logger.exception(f"[TOPS] schedule failed user={user.id}")

    # Глобальный маркер — что топы в этот цикл были отправлены.
    # Это НЕ событие для юзера, а глобальное «мы запускали рассылку».
    # Но hub уже трекает `tops_sent` для каждого юзера, кому ушло.
    # Значит, если scheduled > 0 — cooldown сработает на следующий цикл.
    if scheduled:
        logger.info(f"[TOPS] scheduled={scheduled}")


# ============================================================
# ЦИКЛ
# ============================================================
async def tops_loop(bot: Bot) -> None:
    """
    Фоновый цикл: раз в час.
    Отправляет в воскресенье в 20:00 UTC.
    """
    await asyncio.sleep(INITIAL_DELAY_SECONDS)

    while True:
        try:
            now = datetime.now(timezone.utc)
            if now.weekday() == TOPS_WEEKDAY and now.hour == TOPS_HOUR_UTC:
                await send_weekly_tops(bot)
        except Exception:
            logger.exception("[TOPS] loop iteration failed")

        await asyncio.sleep(CHECK_INTERVAL_SECONDS)