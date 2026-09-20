"""
Логика награды за 10 активных рефералов.
Полная реализация — в этапе 6.2.2.
Пока — заглушка.
"""
from utils.logging import get_logger

logger = get_logger(__name__)


async def check_referral_reward(referrer_id: int, referral_count: int) -> None:
    """
    Проверяет, достиг ли юзер порога 10 активных рефералов.
    Пока — только логирует.
    """
    if referral_count >= 10:
        logger.info(
            f"[REFERRAL_REWARD] user={referrer_id} reached 10 active referrals! "
            f"(feature comes in 6.2.2)"
        )