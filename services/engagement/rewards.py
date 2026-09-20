"""
Универсальная система наград.
Отслеживает, какие разовые награды получены.
Выдаёт whitelist/PRO на N дней.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select

from database.connection import async_session
from database.models import RewardClaim, User
from utils.logging import get_logger

logger = get_logger(__name__)


async def claim_reward(user_id: int, reward_code: str, payload: Optional[dict] = None) -> bool:
    """
    Пытается заклеймить награду.
    Возвращает True, если награда выдана впервые.
    False, если уже была получена.
    """
    async with async_session() as session:
        existing = (await session.execute(
            select(RewardClaim).where(
                RewardClaim.user_id == user_id,
                RewardClaim.reward_code == reward_code,
            )
        )).scalar_one_or_none()

        if existing:
            logger.debug(f"[REWARD] user={user_id} already claimed {reward_code}")
            return False

        session.add(RewardClaim(
            user_id=user_id,
            reward_code=reward_code,
            payload=payload or {},
        ))
        await session.commit()

    logger.info(f"[REWARD] user={user_id} claimed {reward_code}")
    return True


async def has_reward(user_id: int, reward_code: str) -> bool:
    async with async_session() as session:
        existing = (await session.execute(
            select(RewardClaim).where(
                RewardClaim.user_id == user_id,
                RewardClaim.reward_code == reward_code,
            )
        )).scalar_one_or_none()
        return existing is not None


async def grant_pro_days(user_id: int, days: int, reason: str) -> bool:
    """
    Выдаёт PRO на N дней через user.premium_until.
    Если уже есть PRO — продлевает.
    Возвращает True при успехе.
    """
    async with async_session() as session:
        user = (await session.execute(
            select(User).where(User.id == user_id)
        )).scalar_one_or_none()

        if user is None:
            return False

        now = datetime.now(timezone.utc)
        base = user.premium_until if (user.premium_until and user.premium_until > now) else now
        user.premium_until = base + timedelta(days=days)
        await session.commit()

        logger.info(
            f"[REWARD] user={user_id} granted {days}d PRO "
            f"(reason={reason}) until {user.premium_until}"
        )
        return True


async def grant_whitelist_days(user_id: int, days: int, reason: str) -> bool:
    """
    Выдаёт whitelist на N дней (через Whitelist таблицу с expires_at).
    Возвращает True при успехе.
    """
    from database.models import Whitelist

    async with async_session() as session:
        user = (await session.execute(
            select(User).where(User.id == user_id)
        )).scalar_one_or_none()

        if user is None:
            return False

        tg_id = user.telegram_id

        # Проверяем, есть ли уже
        existing = (await session.execute(
            select(Whitelist).where(Whitelist.user_id == tg_id)
        )).scalar_one_or_none()

        now = datetime.now(timezone.utc)
        new_expires = now + timedelta(days=days)

        if existing:
            # Продлеваем
            if existing.expires_at and existing.expires_at > now:
                existing.expires_at = existing.expires_at + timedelta(days=days)
            else:
                existing.expires_at = new_expires
            existing.reason = reason
        else:
            session.add(Whitelist(
                user_id=tg_id,
                reason=reason,
                expires_at=new_expires,
            ))

        await session.commit()

        logger.info(
            f"[REWARD] user={user_id} granted {days}d whitelist (reason={reason})"
        )
        return True