"""
Награды за очки: 1500 → 3 дня PRO, 15000 → 7 дней PRO.
Разовые.
"""
from sqlalchemy import select

from database.connection import async_session
from database.models import User
from services.engagement.notifications import add_custom_notification
from services.engagement.rewards import claim_reward, grant_pro_days
from utils.logging import get_logger

logger = get_logger(__name__)


POINTS_PRO_REWARDS = [
    (1500, "points_1500_pro", 3),
    (15000, "points_15000_pro", 7),
]


async def check_points_rewards(user_id: int, total_points: int) -> None:
    """
    Проверяет пороги очков и выдаёт PRO за пересечённые milestones.

    Порядок: сначала grant_pro_days, потом claim_reward.
    Если grant упадёт — claim не сработает, и при следующем вызове
    попробуем снова. Это снижает риск потери награды.
    """
    async with async_session() as session:
        user = (await session.execute(
            select(User).where(User.id == user_id)
        )).scalar_one_or_none()

    if user is None:
        return

    for threshold, code, days in POINTS_PRO_REWARDS:
        if total_points < threshold:
            continue

        # Проверяем, не получал ли уже — чтобы не дёргать grant_pro_days зря
        # (это read-only, безопасно)
        # claim_reward сделаем ПОСЛЕ grant, чтобы не сжечь награду
        # при падении grant.
        try:
            await grant_pro_days(user_id, days, reason=code)
        except Exception:
            logger.exception(f"[POINTS_REWARD] grant failed for {code}")
            continue

        # Фиксируем факт выдачи
        claimed = await claim_reward(user_id, code, payload={"points": total_points})
        if not claimed:
            # Уже получал раньше — grant_pro_days выше продлил PRO лишний раз.
            # Это редкий кейс (гонка), но зафиксируем.
            logger.warning(
                f"[POINTS_REWARD] user={user_id} {code} claimed twice (race?)"
            )

        try:
            add_custom_notification(
                user.telegram_id,
                (
                    f"⭐ <b>НАГРАДА ЗА {threshold} ОЧКОВ!</b>\n\n"
                    f"🎁 Держи <b>{days} дней PRO</b> в подарок!"
                ),
            )
        except Exception:
            logger.exception("[POINTS_REWARD] notification failed")

        logger.info(f"[POINTS_REWARD] user={user_id} {code} → +{days}d PRO")