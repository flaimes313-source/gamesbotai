"""
Логика реферальной системы.
Считаем только АКТИВНЫХ рефералов (прошли хотя бы 1 анализ).
Очки начисляются пригласившему после первого анализа друга.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, select

from database.connection import async_session
from database.models import (
    PhotoAnalysis,
    ReferralReward,
    User,
    UserEngagement,
)
from services.engagement.points import add_custom_points, get_or_create_engagement
from utils.logging import get_logger

logger = get_logger(__name__)


# Награда за 1 активного реферала
REFERRAL_POINTS = 50

# Считаем только рефералов за последние N дней
REFERRAL_WINDOW_DAYS = 30


async def on_referred_user_analyzed(referred_user_id: int) -> None:
    """
    Вызывается ПОСЛЕ первого анализа фото друга.
    Если у друга есть referrer_id — начисляем очки пригласившему.
    Защита от повторного начисления через ReferralReward.

    referred_user_id — внутренний ID друга (User.id).
    """
    async with async_session() as session:
        # Получаем друга
        referred = (await session.execute(
            select(User).where(User.id == referred_user_id)
        )).scalar_one_or_none()

        if referred is None:
            return

        referrer_id = referred.referrer_id

        # Нет реферала — выходим
        if referrer_id is None:
            return

        # Защита: друг сам себе реферал
        if referrer_id == referred_user_id:
            logger.warning(f"[REFERRAL] user {referred_user_id} has self as referrer")
            return

        # Друг заблокирован — не считаем
        if referred.is_blocked:
            return

        # Проверяем, был ли уже начислён бонус
        existing_reward = (await session.execute(
            select(ReferralReward).where(ReferralReward.referred_id == referred_user_id)
        )).scalar_one_or_none()

        if existing_reward is not None:
            logger.debug(f"[REFERRAL] reward already granted for referred={referred_user_id}")
            return

        # Проверяем окно 30 дней
        created_at = referred.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)

        now = datetime.now(timezone.utc)
        if (now - created_at) > timedelta(days=REFERRAL_WINDOW_DAYS):
            logger.info(f"[REFERRAL] user {referred_user_id} outside 30d window")
            return

        # Получаем пригласившего
        referrer = (await session.execute(
            select(User).where(User.id == referrer_id)
        )).scalar_one_or_none()

        if referrer is None or referrer.is_blocked:
            return

        # Сохраняем награду
        session.add(ReferralReward(
            referrer_id=referrer_id,
            referred_id=referred_user_id,
            points_awarded=REFERRAL_POINTS,
        ))

        # Инкрементируем total_referrals в engagement
        eng = await get_or_create_engagement(session, referrer_id)
        eng.total_referrals += 1

        # Считываем значения ДО commit (чтобы не работать с detached-объектами)
        referrer_user_id = referrer.id
        new_referral_count = eng.total_referrals

        await session.commit()

    logger.info(
        f"[REFERRAL] active referral: referrer={referrer_user_id} "
        f"referred={referred_user_id} total={new_referral_count}"
    )

    # Начисляем очки (вне сессии)
    await add_custom_points(referrer_user_id, REFERRAL_POINTS)

    # Проверяем порог для награды (10 активных)
    try:
        from services.engagement.referral_reward import check_referral_reward
        await check_referral_reward(referrer_user_id, new_referral_count)
    except Exception:
        logger.exception("[REFERRAL] check_referral_reward failed")


async def get_active_referrals_count(referrer_id: int) -> int:
    """Сколько активных рефералов у юзера."""
    async with async_session() as session:
        cnt = (await session.execute(
            select(func.count(ReferralReward.id))
            .where(ReferralReward.referrer_id == referrer_id)
        )).scalar_one()
    return int(cnt or 0)


async def has_referral(user_id: int) -> bool:
    """Есть ли у юзера referrer_id."""
    async with async_session() as session:
        user = (await session.execute(
            select(User).where(User.id == user_id)
        )).scalar_one_or_none()
        return bool(user and user.referrer_id)