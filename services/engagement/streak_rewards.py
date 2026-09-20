"""
Награды за стрики: 7 → 1 день PRO, 30 → 3 дня PRO.
Разовые.
"""
from sqlalchemy import select

from database.connection import async_session
from database.models import User
from services.engagement.notifications import add_custom_notification
from services.engagement.rewards import claim_reward, grant_pro_days
from utils.logging import get_logger

logger = get_logger(__name__)


STREAK_PRO_REWARDS = {
    7: ("streak_7_pro", 1),
    30: ("streak_30_pro", 3),
    100: ("streak_100_pro", 7),
}


async def check_streak_reward(user_id: int, streak: int) -> None:
    """
    Проверяет milestone стрика и выдаёт PRO, если положено.
    Разово.
    """
    reward_data = STREAK_PRO_REWARDS.get(streak)
    if reward_data is None:
        return

    reward_code, days = reward_data

    claimed = await claim_reward(user_id, reward_code, payload={"streak": streak})
    if not claimed:
        return

    async with async_session() as session:
        user = (await session.execute(
            select(User).where(User.id == user_id)
        )).scalar_one_or_none()

    if user is None:
        return

    try:
        await grant_pro_days(user_id, days, reason=reward_code)
    except Exception:
        logger.exception("[STREAK_REWARD] grant failed")
        return

    try:
        add_custom_notification(
            user.telegram_id,
            (
                f"🔥 <b>НАГРАДА ЗА СТРИК {streak} ДНЕЙ!</b>\n\n"
                f"Ты заходил {streak} дней подряд!\n\n"
                f"🎁 Держи <b>{days} дней PRO</b> в подарок!"
            ),
        )
    except Exception:
        logger.exception("[STREAK_REWARD] notification failed")

    logger.info(f"[STREAK_REWARD] user={user_id} streak={streak} → +{days}d PRO")