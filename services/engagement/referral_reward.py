"""
Награда за 10 активных рефералов → 7 дней PRO.
Разовая акция.
"""
from sqlalchemy import select

from database.connection import async_session
from database.models import User
from services.engagement.notifications import add_custom_notification
from services.engagement.rewards import claim_reward, grant_pro_days
from utils.logging import get_logger

logger = get_logger(__name__)


REFERRAL_REWARD_THRESHOLD = 10
REFERRAL_REWARD_CODE = "referral_10_pro"
REFERRAL_REWARD_DAYS = 7


async def check_referral_reward(referrer_id: int, referral_count: int) -> None:
    """
    Проверяет порог 10 активных рефералов.
    Если достиг — выдаёт 7 дней PRO (разово).
    """
    if referral_count < REFERRAL_REWARD_THRESHOLD:
        return

    # Сначала проверяем, что юзер существует
    async with async_session() as session:
        user = (await session.execute(
            select(User).where(User.id == referrer_id)
        )).scalar_one_or_none()

    if user is None:
        logger.warning(f"[REFERRAL_REWARD] user {referrer_id} not found")
        return

    # Пытаемся заклеймить (защита от повторов)
    claimed = await claim_reward(
        referrer_id,
        REFERRAL_REWARD_CODE,
        payload={"referrals": referral_count},
    )

    if not claimed:
        # Уже получал — ничего
        return

    # Выдаём PRO на 7 дней
    try:
        await grant_pro_days(referrer_id, REFERRAL_REWARD_DAYS, reason="referral_10")
    except Exception:
        logger.exception("[REFERRAL_REWARD] grant_pro_days failed")
        return

    # Уведомление
    try:
        add_custom_notification(
            user.telegram_id,
            (
                "🎁 <b>ПОДАРОК РАЗБЛОКИРОВАН!</b>\n\n"
                f"Ты пригласил(а) <b>{referral_count}</b> активных друзей!\n\n"
                f"За это получаешь <b>{REFERRAL_REWARD_DAYS} дней PRO</b> бесплатно!\n\n"
                "Что открылось:\n"
                "• ♾ Безлимит AI-анализов\n"
                "• 🚀 Расширенные режимы поиска\n"
                "• 🤖 AI-помощник в чатах\n"
                "• 🚫 Без рекламы\n"
                "• ✅ Пропуск обязательных подписок\n\n"
                f"PRO активирована на <b>{REFERRAL_REWARD_DAYS} дней</b>. "
                "Пользуйся!"
            ),
        )
    except Exception:
        logger.exception("[REFERRAL_REWARD] notification failed")

    logger.info(
        f"[REFERRAL_REWARD] user={referrer_id} got {REFERRAL_REWARD_DAYS}d PRO"
    )