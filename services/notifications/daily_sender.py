import asyncio
from datetime import datetime, timedelta

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError
from sqlalchemy import select

from database.connection import async_session
from database.models import Profile, User
from services.ai.factory import get_ai_provider
from services.analytics.tracker import track
from utils.logging import get_logger

logger = get_logger(__name__)

DAILY_TARGET_HOUR = 19  # UTC, ~22:00 МСК


async def send_daily_to_all(bot: Bot) -> None:
    """
    Отправляет ежедневный результат всем активным пользователям.
    Запускать раз в день (например, в DAILY_TARGET_HOUR UTC).
    """
    cutoff = datetime.utcnow() - timedelta(days=7)  # активные за 7 дней

    async with async_session() as session:
        users = (await session.execute(
            select(User)
            .where(User.is_blocked.is_(False))
            .where(User.last_active_at >= cutoff)
        )).scalars().all()

    logger.info(f"Daily send: {len(users)} recipients")

    sent = 0
    for user in users:
        try:
            ok = await _send_one(bot, user.telegram_id)
            if ok:
                sent += 1
            # пауза 50ms между сообщениями, чтобы не ловить flood
            await asyncio.sleep(0.05)
        except TelegramForbiddenError:
            # Пользователь заблокировал бота — помечаем
            async with async_session() as session:
                u = (await session.execute(
                    select(User).where(User.telegram_id == user.telegram_id)
                )).scalar_one_or_none()
                if u:
                    u.is_blocked = True
                    await session.commit()
        except Exception:
            logger.exception(f"Daily failed for {user.telegram_id}")

    logger.info(f"Daily sent: {sent}/{len(users)}")


async def _send_one(bot: Bot, telegram_id: int) -> bool:
    async with async_session() as session:
        user = (await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )).scalar_one_or_none()
        if not user:
            return False

        profile = (await session.execute(
            select(Profile).where(Profile.user_id == user.id).order_by(Profile.id.desc()).limit(1)
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
        result = await get_ai_provider().generate_daily_result(profile_dict)
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
    except Exception:
        return False


async def daily_loop(bot: Bot) -> None:
    """
    Фоновая задача: раз в сутки в DAILY_TARGET_HOUR UTC шлёт рассылку.
    """
    while True:
        now = datetime.utcnow()
        target = now.replace(hour=DAILY_TARGET_HOUR, minute=0, second=0, microsecond=0)

        if target <= now:
            target += timedelta(days=1)

        sleep_seconds = (target - now).total_seconds()
        logger.info(f"Daily loop: next run in {sleep_seconds/3600:.1f}h")

        await asyncio.sleep(sleep_seconds)

        try:
            await send_daily_to_all(bot)
        except Exception:
            logger.exception("Daily loop iteration failed")