"""
Планировщик «Гороскоп вайба» (Этап 2).

Раз в 30 минут:
- у кого локально 10:00?
- и сегодня вторник или пятница?
→ готовим гороскоп, ставим в hub.
"""

import asyncio
from datetime import datetime, timezone
from typing import Optional

from aiogram import Bot
from sqlalchemy import select

from database.connection import async_session
from database.models import User
from services.engagement.horoscope import (
    format_horoscope_message,
    prepare_horoscope,
)
from services.notifications.hub import schedule_notification
from services.timezones import get_local_hour
from utils.logging import get_logger

logger = get_logger(__name__)


# ============================================================
# НАСТРОЙКИ
# ============================================================
TARGET_HOUR = 10
# Дни недели: 1 = вторник, 4 = пятница (0 = понедельник)
TARGET_WEEKDAYS = {1, 4}
CHECK_INTERVAL_SECONDS = 30 * 60


# ============================================================
# УТИЛИТА: локальный weekday
# ============================================================
def _get_local_weekday(tz_name: str) -> int:
    """Локальный день недели (0=Пн, 6=Вс)."""
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo(tz_name or "Europe/Moscow")
    except Exception:
        from datetime import timezone as _tz
        tz = _tz.utc
    return datetime.now(tz).weekday()


# ============================================================
# ИТЕРАЦИЯ
# ============================================================
async def send_horoscope_for_current_hour(bot: Bot) -> None:
    """
    Проходит по юзерам с локальным 10:00 во вт/пт и ставит в hub.
    """
    async with async_session() as session:
        users = (await session.execute(
            select(User).where(User.is_blocked.is_(False))
        )).scalars().all()

    scheduled = 0
    for user in users:
        # Локальное 10:00?
        if get_local_hour(user.timezone) != TARGET_HOUR:
            continue

        # Сегодня вт или пт?
        if _get_local_weekday(user.timezone) not in TARGET_WEEKDAYS:
            continue

        # Готовим гороскоп
        payload = await prepare_horoscope(user.id)
        if payload is None:
            continue

        text = format_horoscope_message(payload["text"])

        ok = await schedule_notification(
            user_id=user.id,
            kind="horoscope",
            priority=3,
            payload={"text": text},
            tz_name=user.timezone,
        )

        if ok:
            scheduled += 1
            logger.info(f"[HOROSCOPE] queued user={user.id}")

    if scheduled:
        logger.info(f"[HOROSCOPE] scheduled={scheduled}")


# ============================================================
# ЦИКЛ
# ============================================================
async def horoscope_loop(bot: Bot) -> None:
    """
    Бесконечный цикл: раз в 30 минут проверяем TZ юзеров.
    """
    while True:
        try:
            await send_horoscope_for_current_hour(bot)
        except Exception:
            logger.exception("[HOROSCOPE] loop iteration failed")

        await asyncio.sleep(CHECK_INTERVAL_SECONDS)