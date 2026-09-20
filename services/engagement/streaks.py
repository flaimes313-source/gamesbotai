"""
Серии дней (стрики).
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select

from database.connection import async_session
from database.models import User, UserEngagement
from services.engagement.points import add_points
from utils.logging import get_logger

logger = get_logger(__name__)


STREAK_MILESTONES = {
    3: "streak_3",
    7: "streak_7",
    14: "streak_14",
    30: "streak_30",
    100: "streak_100",
}


async def update_streak(user_id: int) -> dict:
    today = datetime.now(timezone.utc).date()

    async with async_session() as session:
        eng = (await session.execute(
            select(UserEngagement).where(UserEngagement.user_id == user_id)
        )).scalar_one_or_none()

        if eng is None:
            eng = UserEngagement(
                user_id=user_id,
                current_streak=1,
                max_streak=1,
                last_visit_date=datetime.now(timezone.utc),
            )
            session.add(eng)
            await session.commit()
            await add_points(user_id, "first_login")
            return {
                "current_streak": 1,
                "is_new_day": True,
                "streak_milestone": None,
            }

        last_visit = eng.last_visit_date.date() if eng.last_visit_date else None

        if last_visit == today:
            return {
                "current_streak": eng.current_streak,
                "is_new_day": False,
                "streak_milestone": None,
            }

        yesterday = today - timedelta(days=1)

        if last_visit == yesterday:
            eng.current_streak += 1
        else:
            eng.current_streak = 1

        if eng.current_streak > eng.max_streak:
            eng.max_streak = eng.current_streak

        eng.last_visit_date = datetime.now(timezone.utc)
        streak = eng.current_streak
        await session.commit()

    await add_points(user_id, "daily_login")

    if streak > 1:
        await add_points(user_id, "streak_bonus", multiplier=streak)

    milestone = STREAK_MILESTONES.get(streak)

    if milestone:
        try:
            from services.achievements import unlock_achievement
            is_new = await unlock_achievement(user_id, milestone)
            if is_new:
                logger.info(f"[STREAK] Unlocked {milestone} for user={user_id}")
        except Exception:
            logger.exception(f"[STREAK] Failed to unlock {milestone}")

        try:
            from services.engagement.notifications import add_streak_notification
            async with async_session() as session:
                user = (await session.execute(
                    select(User).where(User.id == user_id)
                )).scalar_one_or_none()
            if user:
                add_streak_notification(user.telegram_id, streak)
        except Exception:
            logger.exception("[STREAK] Failed to queue streak notification")

        # 🎁 Награда за стрик (PRO)
        try:
            from services.engagement.streak_rewards import check_streak_reward
            await check_streak_reward(user_id, streak)
        except Exception:
            logger.exception("[STREAK] check_streak_reward failed")

    logger.info(f"[STREAK] user={user_id} streak={streak} milestone={milestone}")

    return {
        "current_streak": streak,
        "is_new_day": True,
        "streak_milestone": milestone,
    }


async def get_streak(user_id: int) -> int:
    async with async_session() as session:
        eng = (await session.execute(
            select(UserEngagement).where(UserEngagement.user_id == user_id)
        )).scalar_one_or_none()
        return eng.current_streak if eng else 0