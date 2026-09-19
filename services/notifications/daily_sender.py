import asyncio
from datetime import datetime, timedelta, timezone

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError
from sqlalchemy import func, select

from database.connection import async_session
from database.models import Event, Profile, User
from services.ai.factory import get_ai_provider
from services.analytics.tracker import track
from services.feature_flags import is_enabled
from services.timezones import get_local_hour
from utils.logging import get_logger

logger = get_logger(__name__)

DAILY_TARGET_HOUR = 20
CHECK_INTERVAL_SECONDS = 15 * 60


async def _send_one(bot: Bot, telegram_id: int) -> bool:
    async with async_session() as session:
        user = (await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )).scalar_one_or_none()
        if not user:
            return False

        profile = (await session.execute(
            select(Profile)
            .where(Profile.user_id == user.id)
            .order_by(Profile.id.desc())
            .limit(1)
        )).scalar_one_or_none()

    if profile is None:
        return False

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
        logger.exception("Daily AI failed")
        return False

    try:
        await bot.send_message(
            telegram_id,
            f"{result.get('emoji', '✨')} <b>{result.get('title', '')}</b>\n\n"
            f"{result.get('text', '')}\n\n"
            "Хочешь новый анализ? Отправь фото 📸"
        )
        await track("daily_sent", telegram_id=telegram_id)
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
        logger.exception(f"Daily send failed for {telegram_id}")
        return False


async def send_daily_for_current_hour(bot: Bot) -> None:
    if not await is_enabled("daily_content_enabled", default=False):
        return

    cutoff = datetime.now(timezone.utc) - timedelta(days=7)

    async with async_session() as session:
        users = (await session.execute(
            select(User)
            .where(User.is_blocked.is_(False))
            .where(User.last_active_at >= cutoff)
        )).scalars().all()

    sent = 0
    for user in users:
        if get_local_hour(user.timezone) != DAILY_TARGET_HOUR:
            continue

        today_start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        async with async_session() as session:
            already = (await session.execute(
                select(func.count(Event.id))
                .where(Event.name == "daily_sent")
                .where(Event.telegram_id == user.telegram_id)
                .where(Event.created_at >= today_start)
            )).scalar_one()

            if already > 0:
                continue

        try:
            ok = await _send_one(bot, user.telegram_id)
            if ok:
                sent += 1
            await asyncio.sleep(0.05)
        except Exception:
            logger.exception(f"Daily failed for {user.telegram_id}")

    if sent:
        logger.info(f"Daily sent to {sent} users")


async def daily_loop(bot: Bot) -> None:
    while True:
        try:
            await send_daily_for_current_hour(bot)
        except Exception:
            logger.exception("Daily loop iteration failed")

        await asyncio.sleep(CHECK_INTERVAL_SECONDS)