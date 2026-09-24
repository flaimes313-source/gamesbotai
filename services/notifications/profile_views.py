"""
Планировщик «Кто посмотрел профиль» (Этап 3).

Раз в час:
- для юзеров, у которых локально 18:00
- проверяем: есть реальные просмотры за 7 дней?
    → да: шлём «N человек зашли» (priority=3)
- или юзера не было 4+ дней?
    → да: шлём псевдо «твой вайб ждут» (priority=4)
"""

import asyncio
from datetime import datetime, timedelta, timezone

from aiogram import Bot
from sqlalchemy import select

from database.connection import async_session
from database.models import User
from services.notifications.hub import schedule_notification
from services.social.profile_views import (
    MIN_DAYS_AWAY_FOR_PSEUDO,
    format_profile_views_message,
    get_pseudo_views,
    get_recent_viewers_count,
    get_viewers_archetypes,
)
from services.timezones import get_local_hour
from utils.logging import get_logger

logger = get_logger(__name__)


TARGET_HOUR = 18
CHECK_INTERVAL_SECONDS = 60 * 60   # 1 час


async def send_profile_views_for_current_hour(bot: Bot) -> None:
    async with async_session() as session:
        users = (await session.execute(
            select(User).where(User.is_blocked.is_(False))
        )).scalars().all()

    scheduled = 0
    for user in users:
        if get_local_hour(user.timezone) != TARGET_HOUR:
            continue

        # 1. Пробуем реальные
        real_count = await get_recent_viewers_count(user.id)

        message_text = ""
        priority = 4

        if real_count > 0:
            archetypes = await get_viewers_archetypes(user.id)
            message_text = format_profile_views_message(
                real_count=real_count,
                archetypes=archetypes,
            )
            priority = 3
        else:
            # 2. Псевдо для отсутствующих
            pseudo = get_pseudo_views(user.last_active_at)
            if pseudo:
                message_text = format_profile_views_message(
                    real_count=0,
                    archetypes=[],
                    pseudo=pseudo,
                )

        if not message_text:
            continue

        ok = await schedule_notification(
            user_id=user.id,
            kind="profile_views",
            priority=priority,
            payload={"text": message_text},
            tz_name=user.timezone,
        )
        if ok:
            scheduled += 1
            logger.info(f"[VIEWS] queued user={user.id} real={real_count}")

    if scheduled:
        logger.info(f"[VIEWS] scheduled={scheduled}")


async def profile_views_loop(bot: Bot) -> None:
    while True:
        try:
            await send_profile_views_for_current_hour(bot)
        except Exception:
            logger.exception("[VIEWS] loop iteration failed")

        await asyncio.sleep(CHECK_INTERVAL_SECONDS)