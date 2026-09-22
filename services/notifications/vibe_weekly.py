"""
Недельная рассылка вайб-отчётов (Шаг 1.3.2).

Каждое воскресенье в 19:00 по TZ юзера:
- если юзер был активен >= MIN_ACTIVE_DAYS_FOR_WEEKLY (3) дней за 7 дней,
- и ему ещё не слали сегодня,
→ отправляем:
    * карточку «Твой вайб-месяц» (PNG),
    * caption с коротким текстом,
    * recommendation.

Стиль — как в daily_sender.py:
- asyncio-цикл,
- проверка TZ через get_local_hour,
- защита от дублей через events,
- TelegramForbiddenError → is_blocked=True.
"""

import asyncio
from datetime import datetime, timedelta, timezone

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError
from sqlalchemy import func, select

from database.connection import async_session
from database.models import Event, Profile, User
from services.analysis.vibe_report import build_vibe_report
from services.analytics.tracker import track
from services.cards.vibe_summary import generate_vibe_summary_card
from services.feature_flags import is_enabled
from services.timezones import get_local_hour
from utils.logging import get_logger

logger = get_logger(__name__)


# ============================================================
# НАСТРОЙКИ
# ============================================================
WEEKLY_TARGET_HOUR = 19          # 19:00 по локальному TZ юзера
WEEKLY_TARGET_WEEKDAY = 6        # 6 = воскресенье (0=пн, 6=вс)
MIN_ACTIVE_DAYS_FOR_WEEKLY = 3   # сколько дней из 7 должен быть активен
CHECK_INTERVAL_SECONDS = 15 * 60 # проверка каждые 15 минут


# ============================================================
# ВСПОМОГАТЕЛЬНОЕ: локальный weekday
# ============================================================
def _get_local_weekday(tz_name: str) -> int:
    """
    Возвращает локальный день недели (0=Пн, 6=Вс) для TZ юзера.
    Пытается через zoneinfo, откат — UTC.
    """
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo(tz_name or "Europe/Moscow")
    except Exception:
        tz = timezone.utc
    return datetime.now(tz).weekday()


# ============================================================
# ВСПОМОГАТЕЛЬНОЕ: активные дни за неделю
# ============================================================
async def _count_active_days_week(user_id: int) -> int:
    """
    Считает кол-во уникальных дней за последние 7 дней,
    в которые юзер был активен (по events).
    """
    since = datetime.now(timezone.utc) - timedelta(days=7)

    try:
        async with async_session() as session:
            rows = (await session.execute(
                select(func.date(Event.created_at))
                .where(Event.user_id == user_id)
                .where(Event.created_at >= since)
                .where(Event.name.in_([
                    "new_users",
                    "photo_sent",
                    "analysis_started",
                    "share_generated",
                    "chat_message_sent",
                    "test_started",
                    "challenge_viewed",
                ]))
                .distinct()
            )).scalars().all()
            return len(rows)
    except Exception:
        logger.exception("[VIBE_WEEKLY] active_days failed")
        return 0


# ============================================================
# ВСПОМОГАТЕЛЬНОЕ: уже слали сегодня?
# ============================================================
async def _already_sent_today(telegram_id: int) -> bool:
    today_start = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    try:
        async with async_session() as session:
            cnt = (await session.execute(
                select(func.count(Event.id))
                .where(Event.name == "vibe_weekly_sent")
                .where(Event.telegram_id == telegram_id)
                .where(Event.created_at >= today_start)
            )).scalar_one()
            return cnt > 0
    except Exception:
        logger.exception("[VIBE_WEEKLY] already_sent check failed")
        return False


# ============================================================
# ОТПРАВКА ОДНОМУ ЮЗЕРУ
# ============================================================
async def _send_one(bot: Bot, telegram_id: int, user_id: int) -> bool:
    """
    Собирает и отправляет недельный отчёт одному юзеру.
    Возвращает True, если успешно.
    """
    # 1. Недельный отчёт (проверка active_days внутри — уже прошла)
    try:
        report = await build_vibe_report(user_id, weekly=True)
    except Exception:
        logger.exception(f"[VIBE_WEEKLY] build failed for {telegram_id}")
        return False

    if not report.get("available"):
        return False

    # 2. Данные для карточки
    # Нам нужны метрики — соберём их отдельным запросом
    try:
        async with async_session() as session:
            user = (await session.execute(
                select(User).where(User.id == user_id)
            )).scalar_one_or_none()

            if user is None:
                return False

            profile = (await session.execute(
                select(Profile)
                .where(Profile.user_id == user_id)
                .order_by(Profile.id.desc())
                .limit(1)
            )).scalar_one_or_none()

            last_archetype = profile.archetype if profile else None

            from database.models import UserEngagement
            eng = (await session.execute(
                select(UserEngagement).where(UserEngagement.user_id == user_id)
            )).scalar_one_or_none()

            # Активные дни за неделю
            active_days = await _count_active_days_week(user_id)

            # Уникальные архетипы — из коллекции
            archetypes_collected = (
                eng.archetypes_collected or {}
            ) if eng else {}
            unique_archetypes = len(archetypes_collected)

            # Легендарных
            from services.analysis.rarity import is_legendary
            legendary_count = sum(
                1 for a in archetypes_collected.keys()
                if is_legendary(a)
            )

            stats = {
                "total_analyses": eng.total_analyses if eng else 0,
                "total_points": eng.total_points if eng else 0,
                "current_streak": eng.current_streak if eng else 0,
                "active_days": active_days,
                "unique_archetypes": unique_archetypes,
                "legendary_count": legendary_count,
            }
    except Exception:
        logger.exception(f"[VIBE_WEEKLY] stats collect failed for {telegram_id}")
        return False

    # 3. Период — «Неделя: DD.MM — DD.MM»
    now_utc = datetime.now(timezone.utc)
    week_end = now_utc.date()
    week_start = (now_utc - timedelta(days=6)).date()
    period_label = (
        f"Неделя: {week_start.strftime('%d.%m')} — {week_end.strftime('%d.%m')}"
    )

    # 4. bot_username
    try:
        me = await bot.get_me()
        bot_username = me.username
    except Exception:
        bot_username = None

    # 5. Карточка
    try:
        card_bytes = generate_vibe_summary_card(
            summary=report.get("summary", ""),
            stats=stats,
            archetype=last_archetype,
            bot_username=bot_username,
            period_label=period_label,
        )
    except Exception:
        logger.exception(f"[VIBE_WEEKLY] card gen failed for {telegram_id}")
        card_bytes = None

    # 6. Caption
    summary_line = (report.get("summary") or "").strip()
    recommendation = (report.get("recommendation") or "").strip()

    caption_parts = ["🗓 <b>ТВОЙ ВАЙБ-МЕСЯЦ</b>"]
    if summary_line:
        caption_parts.append(f"\n✨ <i>{summary_line}</i>")
    if active_days := stats.get("active_days"):
        caption_parts.append(
            f"\n\n📅 Ты был активен <b>{active_days} из 7</b> дней!"
        )
    if recommendation:
        caption_parts.append(f"\n\n💡 <b>Совет:</b> {recommendation}")
    caption_parts.append("\n\n👇 Открой полный отчёт в профиле.")

    caption = "".join(caption_parts)

    # 7. Отправка
    try:
        from aiogram.types import BufferedInputFile
        if card_bytes:
            await bot.send_photo(
                telegram_id,
                BufferedInputFile(card_bytes, filename="vibe_week.png"),
                caption=caption,
            )
        else:
            # Fallback — только текст
            await bot.send_message(telegram_id, caption)

        await track(
            "vibe_weekly_sent",
            telegram_id=telegram_id,
            payload={
                "active_days": active_days,
                "had_card": card_bytes is not None,
            },
        )
        return True

    except TelegramForbiddenError:
        async with async_session() as session:
            u = (await session.execute(
                select(User).where(User.telegram_id == telegram_id)
            )).scalar_one_or_none()
            if u:
                u.is_blocked = True
                await session.commit()
        return False
    except Exception:
        logger.exception(f"[VIBE_WEEKLY] send failed for {telegram_id}")
        return False


# ============================================================
# ИТЕРАЦИЯ ПО ЮЗЕРАМ
# ============================================================
async def send_weekly_for_current_hour(bot: Bot) -> None:
    """
    Проходит по юзерам, у которых СЕЙЧАС локально воскресенье 19:00.
    Отправляет только активным (>= 3 дней) и только раз в день.
    """
    # Проверка feature flag — если нет, используем дефолт True
    # (фича новая, сразу включаем)
    if not await is_enabled("weekly_vibe_enabled", default=True):
        return

    now_utc = datetime.now(timezone.utc)
    cutoff = now_utc - timedelta(days=14)  # активные за 2 недели

    async with async_session() as session:
        users = (await session.execute(
            select(User)
            .where(User.is_blocked.is_(False))
            .where(User.last_active_at >= cutoff)
        )).scalars().all()

    sent = 0
    skipped_inactive = 0

    for user in users:
        # Локальное время: воскресенье 19:00?
        if get_local_hour(user.timezone) != WEEKLY_TARGET_HOUR:
            continue
        if _get_local_weekday(user.timezone) != WEEKLY_TARGET_WEEKDAY:
            continue

        # Уже слали сегодня?
        if await _already_sent_today(user.telegram_id):
            continue

        # Активные дни за неделю
        active_days = await _count_active_days_week(user.id)
        if active_days < MIN_ACTIVE_DAYS_FOR_WEEKLY:
            skipped_inactive += 1
            continue

        try:
            ok = await _send_one(bot, user.telegram_id, user.id)
            if ok:
                sent += 1
            await asyncio.sleep(0.05)
        except Exception:
            logger.exception(f"[VIBE_WEEKLY] failed for {user.telegram_id}")

    if sent or skipped_inactive:
        logger.info(
            f"[VIBE_WEEKLY] sent={sent} skipped_inactive={skipped_inactive}"
        )


# ============================================================
# ЦИКЛ ПЛАНИРОВЩИКА
# ============================================================
async def weekly_vibe_loop(bot: Bot) -> None:
    """
    Бесконечный цикл: раз в 15 минут проверяем,
    не наступило ли у кого-то воскресенье 19:00.
    """
    while True:
        try:
            await send_weekly_for_current_hour(bot)
        except Exception:
            logger.exception("[VIBE_WEEKLY] loop iteration failed")

        await asyncio.sleep(CHECK_INTERVAL_SECONDS)