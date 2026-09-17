from sqlalchemy import select
from database.connection import async_session
from database.models import Profile, User
from services.ai.factory import get_ai_provider
from utils.logging import get_logger

logger = get_logger(__name__)


async def send_daily_result(bot, telegram_id: int) -> None:
    async with async_session() as session:
        user = (await session.execute(select(User).where(User.telegram_id == telegram_id))).scalar_one_or_none()
        if not user:
            return
        profile = (await session.execute(
            select(Profile).where(Profile.user_id == user.id).order_by(Profile.id.desc()).limit(1)
        )).scalar_one_or_none()

    if profile is None:
        return

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
        logger.exception("Daily result failed")
        return

    try:
        await bot.send_message(
            telegram_id,
            f"{result.get('emoji', '✨')} <b>{result.get('title', '')}</b>\n\n{result.get('text', '')}",
        )
    except Exception:
        logger.exception("Send daily failed")