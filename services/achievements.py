from sqlalchemy import select
from database.connection import async_session
from database.models import Achievement, UserAchievement
from utils.logging import get_logger

logger = get_logger(__name__)


async def unlock_achievement(user_id: int, code: str) -> bool:
    """Возвращает True, если достижение выдано впервые."""
    async with async_session() as session:
        existing = (await session.execute(
            select(UserAchievement).where(
                UserAchievement.user_id == user_id,
                UserAchievement.achievement_code == code,
            )
        )).scalar_one_or_none()

        if existing:
            return False

        session.add(UserAchievement(user_id=user_id, achievement_code=code))
        await session.commit()
        logger.info(f"Achievement unlocked: user={user_id} code={code}")
        return True


async def list_user_achievements(user_id: int):
    async with async_session() as session:
        codes = [r.achievement_code for r in (await session.execute(
            select(UserAchievement).where(UserAchievement.user_id == user_id)
        )).scalars().all()]
        achievements = (await session.execute(
            select(Achievement).where(Achievement.code.in_(codes))
        )).scalars().all()
        return achievements