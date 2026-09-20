from sqlalchemy import select

from database.connection import async_session
from database.models import Achievement, User, UserAchievement
from utils.logging import get_logger

logger = get_logger(__name__)


async def unlock_achievement(user_id: int, code: str) -> bool:
    """
    Возвращает True, если достижение выдано впервые.
    При успехе добавляет уведомление в очередь.
    """
    async with async_session() as session:
        # Проверяем, есть ли
        existing = (await session.execute(
            select(UserAchievement).where(
                UserAchievement.user_id == user_id,
                UserAchievement.achievement_code == code,
            )
        )).scalar_one_or_none()

        if existing:
            return False

        # Находим данные достижения
        achievement = (await session.execute(
            select(Achievement).where(Achievement.code == code)
        )).scalar_one_or_none()

        if achievement is None:
            logger.warning(f"Achievement code not found: {code}")
            return False

        # Находим telegram_id юзера
        user = (await session.execute(
            select(User).where(User.id == user_id)
        )).scalar_one_or_none()

        # Сохраняем
        session.add(UserAchievement(user_id=user_id, achievement_code=code))
        await session.commit()

    logger.info(f"Achievement unlocked: user={user_id} code={code}")

    # Добавляем уведомление в очередь
    if user:
        try:
            from services.engagement.notifications import add_achievement_notification
            add_achievement_notification(
                user.telegram_id,
                title=achievement.title,
                description=achievement.description,
                emoji=achievement.emoji,
            )
        except Exception:
            logger.exception("Failed to queue achievement notification")

    return True


async def list_user_achievements(user_id: int):
    async with async_session() as session:
        codes = [
            r.achievement_code
            for r in (await session.execute(
                select(UserAchievement).where(UserAchievement.user_id == user_id)
            )).scalars().all()
        ]
        achievements = (await session.execute(
            select(Achievement).where(Achievement.code.in_(codes))
        )).scalars().all()
        return achievements