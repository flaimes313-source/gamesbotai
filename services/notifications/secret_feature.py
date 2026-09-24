"""
Планировщик «Секретной фичи дня» (Этап 2).

Раз в 30 минут проверяет: у кого сейчас локально 13:00?
Для каждого:
- если юзера не было 2+ дня → ставит в очередь hub подсказку.

Отправка — через hub, чтобы соблюдать лимиты/тихие часы.
"""

import asyncio
from datetime import datetime, timezone

from aiogram import Bot
from sqlalchemy import select

from database.connection import async_session
from database.models import User
from services.engagement.secret_feature import (
    mark_tip_seen,
    prepare_secret_feature,
    should_send,
)
from services.notifications.hub import schedule_notification
from services.timezones import get_local_hour
from utils.logging import get_logger

logger = get_logger(__name__)


# ============================================================
# НАСТРОЙКИ
# ============================================================
TARGET_HOUR = 13
CHECK_INTERVAL_SECONDS = 30 * 60   # 30 минут


# ============================================================
# ИТЕРАЦИЯ
# ============================================================
async def send_secret_feature_for_current_hour(bot: Bot) -> None:
    """
    Проходит по юзерам с локальным 13:00, ставит уведомления в hub.
    """
    # Берём только тех, кто не был 2-60 дней (отсекаем самых мёртвых)
    async with async_session() as session:
        users = (await session.execute(
            select(User)
            .where(User.is_blocked.is_(False))
        )).scalars().all()

    scheduled = 0
    for user in users:
        # Локальное 13:00?
        if get_local_hour(user.timezone) != TARGET_HOUR:
            continue

        # Не был 2+ дня?
        if not should_send(user.last_active_at):
            continue

        # Готовим payload
        payload = await prepare_secret_feature(user.id)
        if payload is None:
            continue

        # Ставим в hub (hub сам проверит флаги, настройки, дубли)
        ok = await schedule_notification(
            user_id=user.id,
            kind="secret_feature",
            priority=4,   # низкий приоритет — если лимит набран, отбросится
            payload={
                "text": payload["text"],
            },
            tz_name=user.timezone,
        )

        if ok:
            # Помечаем подсказку как показанную СРАЗУ (атомарно).
            # Если hub не отправит (лимит/тихие часы) — потеряем подсказку,
            # но это ок: следующий раз выберется другая.
            await mark_tip_seen(user.id, payload["tip_code"])
            scheduled += 1
            logger.info(
                f"[SECRET] queued user={user.id} tip={payload['tip_code']}"
            )

    if scheduled:
        logger.info(f"[SECRET] scheduled={scheduled}")


# ============================================================
# ЦИКЛ
# ============================================================
async def secret_feature_loop(bot: Bot) -> None:
    """
    Бесконечный цикл: раз в 30 минут проверяем TZ юзеров.
    """
    while True:
        try:
            await send_secret_feature_for_current_hour(bot)
        except Exception:
            logger.exception("[SECRET] loop iteration failed")

        await asyncio.sleep(CHECK_INTERVAL_SECONDS)