"""
Награды за стрики: 7 → 1 день PRO, 30 → 3 дня PRO, 100 → 7 дней PRO.
Разовые.

ВАЖНО: порядок claim → grant.
- Сначала claim_reward (атомарно фиксирует факт).
- Потом grant_pro_days (начисляет PRO).
- Если claim не прошёл (уже получал) — grant НЕ вызывается.
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

    Порядок: claim_reward → grant_pro_days.
    """
    reward_data = STREAK_PRO_REWARDS.get(streak)
    if reward_data is None:
        return

    reward_code, days = reward_data

    # Сначала проверяем, что юзер существует
    async with async_session() as session:
        user = (await session.execute(
            select(User).where(User.id == user_id)
        )).scalar_one_or_none()

    if user is None:
        logger.warning(f"[STREAK_REWARD] user {user_id} not found")
        return

    telegram_id = user.telegram_id

    # 1. Атомарно фиксируем факт выдачи. Если уже получал — пропускаем.
    try:
        claimed = await claim_reward(
            user_id,
            reward_code,
            payload={"streak": streak},
        )
    except Exception:
        logger.exception(f"[STREAK_REWARD] claim failed for {reward_code}")
        return

    if not claimed:
        # Уже получал — не выдаём PRO повторно
        return

    # 2. Начисляем PRO
    try:
        await grant_pro_days(user_id, days, reason=reward_code)
    except Exception:
        logger.exception(
            f"[STREAK_REWARD] grant failed for {reward_code} (user={user_id}). "
            f"PRO не начислен, но reward {reward_code} уже зафиксирован."
        )
        return

    # 3. Уведомление
    try:
        add_custom_notification(
            telegram_id,
            (
                f"🔥 <b>НАГРАДА ЗА СТРИК {streak} ДНЕЙ!</b>\n\n"
                f"Ты заходил {streak} дней подряд!\n\n"
                f"🎁 Держи <b>{days} дней PRO</b> в подарок!"
            ),
        )
    except Exception:
        logger.exception("[STREAK_REWARD] notification failed")

    logger.info(f"[STREAK_REWARD] user={user_id} streak={streak} → +{days}d PRO")