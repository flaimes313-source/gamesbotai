"""
Награды за очки: 1500 → 3 дня PRO, 15000 → 7 дней PRO.
Разовые.

ВАЖНО: порядок claim → grant.
- Сначала claim_reward (атомарно фиксирует факт).
- Потом grant_pro_days (начисляет PRO).
- Если claim не прошёл (уже получал) — grant НЕ вызывается.

Это гарантирует, что PRO начислится ровно один раз.
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

    Порядок: claim_reward → grant_pro_days.

    Если claim не прошёл (уже получал) — grant не вызывается.
    """
    async with async_session() as session:
        user = (await session.execute(
            select(User).where(User.id == user_id)
        )).scalar_one_or_none()

    if user is None:
        return

    telegram_id = user.telegram_id

    for threshold, code, days in POINTS_PRO_REWARDS:
        if total_points < threshold:
            continue

        # 1. Атомарно фиксируем факт выдачи. Если уже получал — пропускаем.
        try:
            claimed = await claim_reward(
                user_id,
                code,
                payload={"points": total_points},
            )
        except Exception:
            logger.exception(f"[POINTS_REWARD] claim failed for {code}")
            continue

        if not claimed:
            # Уже получал — не выдаём PRO повторно
            continue

        # 2. Начисляем PRO. Если упадёт — claim уже записан,
        #    награда не повторится. Запишем ошибку в лог.
        try:
            await grant_pro_days(user_id, days, reason=code)
        except Exception:
            logger.exception(
                f"[POINTS_REWARD] grant failed for {code} (user={user_id}). "
                f"PRO не начислен, но reward {code} уже зафиксирован."
            )
            # Не откатываем claim — иначе получим бесконечные попытки.
            continue

        # 3. Уведомление
        try:
            add_custom_notification(
                telegram_id,
                (
                    f"⭐ <b>НАГРАДА ЗА {threshold} ОЧКОВ!</b>\n\n"
                    f"🎁 Держи <b>{days} дней PRO</b> в подарок!"
                ),
            )
        except Exception:
            logger.exception("[POINTS_REWARD] notification failed")

        logger.info(f"[POINTS_REWARD] user={user_id} {code} → +{days}d PRO")