"""
Ежедневный прикол (daily result) — через hub (Этап 4).

Логика:
- Раз в 15 минут проверяем: у кого локально 20:00?
- Генерим персональный прикол через AI.
- Ставим в hub (kind="daily_result", priority=2).

Hub сам проверит:
- feature flag daily_content_enabled,
- настройки юзера (daily_result_enabled),
- тихие часы (23:00–08:00 TZ),
- дневной лимит (2 проактивных),
- дубли (daily_sent сегодня?).

Приоритет 2 — высокий. Если дневной лимит набран,
daily result всё равно пройдёт.
"""

import asyncio
from datetime import datetime, timedelta, timezone

from aiogram import Bot
from sqlalchemy import select

from database.connection import async_session
from database.models import Profile, User
from services.ai.factory import get_ai_provider
from services.feature_flags import is_enabled
from services.notifications.hub import schedule_notification
from services.timezones import get_local_hour
from utils.logging import get_logger

logger = get_logger(__name__)


# ============================================================
# НАСТРОЙКИ
# ============================================================
DAILY_TARGET_HOUR = 20
CHECK_INTERVAL_SECONDS = 15 * 60
DAILY_PRIORITY = 2  # высокий


# ============================================================
# ГЕНЕРАЦИЯ КОНТЕНТА
# ============================================================
async def _build_daily_payload(user_id: int) -> str | None:
    """
    Генерирует текст прикола для юзера.
    Возвращает текст или None, если не получилось.
    """
    async with async_session() as session:
        profile = (await session.execute(
            select(Profile)
            .where(Profile.user_id == user_id)
            .order_by(Profile.id.desc())
            .limit(1)
        )).scalar_one_or_none()

    if profile is None:
        return None

    profile_dict = {
        "archetype": profile.archetype,
        "charisma": profile.charisma,
        "humor": profile.humor,
        "energy": profile.energy,
        "chaos": profile.chaos,
        "creativity": profile.creativity,
    }

    try:
        provider = await get_ai_provider()
        result = await provider.generate_daily_result(profile_dict)
    except Exception:
        logger.exception(f"[DAILY] AI failed user={user_id}")
        return None

    emoji = result.get("emoji", "✨")
    title = result.get("title", "")
    text = result.get("text", "")

    if not (title or text):
        return None

    return (
        f"{emoji} <b>{title}</b>\n\n"
        f"{text}\n\n"
        "Хочешь новый анализ? Отправь фото 📸"
    )


# ============================================================
# ИТЕРАЦИЯ
# ============================================================
async def send_daily_for_current_hour(bot: Bot) -> None:
    """
    Проходит по юзерам с локальным 20:00, ставит в hub.
    """
    if not await is_enabled("daily_content_enabled", default=False):
        return

    cutoff = datetime.now(timezone.utc) - timedelta(days=7)

    async with async_session() as session:
        users = (await session.execute(
            select(User)
            .where(User.is_blocked.is_(False))
            .where(User.last_active_at >= cutoff)
        )).scalars().all()

    scheduled = 0
    for user in users:
        if get_local_hour(user.timezone) != DAILY_TARGET_HOUR:
            continue

        try:
            text = await _build_daily_payload(user.id)
            if not text:
                continue

            ok = await schedule_notification(
                user_id=user.id,
                kind="daily_result",
                priority=DAILY_PRIORITY,
                payload={"text": text},
                tz_name=user.timezone,
            )
            if ok:
                scheduled += 1
        except Exception:
            logger.exception(f"[DAILY] failed user={user.telegram_id}")

    if scheduled:
        logger.info(f"[DAILY] scheduled={scheduled}")


# ============================================================
# ЦИКЛ
# ============================================================
async def daily_loop(bot: Bot) -> None:
    while True:
        try:
            await send_daily_for_current_hour(bot)
        except Exception:
            logger.exception("[DAILY] loop iteration failed")

        await asyncio.sleep(CHECK_INTERVAL_SECONDS)