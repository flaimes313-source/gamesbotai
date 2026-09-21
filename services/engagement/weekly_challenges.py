"""
Еженедельные челленджи.
"""
import random
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select

from database.connection import async_session
from database.models import UserWeeklyChallenge, WeeklyChallenge
from services.engagement.points import add_custom_points
from utils.logging import get_logger

logger = get_logger(__name__)


WEEKLY_POOL = [
    {
        "title": "Марафон анализов",
        "description": "Сделай 5 AI-анализов за неделю",
        "task_type": "photo",
        "target_value": 5,
        "reward_points": 250,
    },
    {
        "title": "Пригласи 3 друзей",
        "description": "Пригласи 3 активных друга за неделю",
        "task_type": "invite",
        "target_value": 3,
        "reward_points": 300,
    },
    {
        "title": "Общительный",
        "description": "Отправь 10 сообщений за неделю",
        "task_type": "message",
        "target_value": 10,
        "reward_points": 200,
    },
    {
        "title": "Сравни себя",
        "description": "Сравнись с 3 игроками за неделю",
        "task_type": "compare",
        "target_value": 3,
        "reward_points": 150,
    },
    {
        "title": "Тестировщик",
        "description": "Пройди 3 теста за неделю",
        "task_type": "test",
        "target_value": 3,
        "reward_points": 250,
    },
]


def _week_start() -> datetime:
    """Понедельник текущей недели, 00:00 UTC."""
    now = datetime.now(timezone.utc)
    monday = now - timedelta(days=now.weekday())
    return monday.replace(hour=0, minute=0, second=0, microsecond=0)


async def get_or_create_weekly_challenge() -> Optional[WeeklyChallenge]:
    week_start = _week_start()

    async with async_session() as session:
        existing = (await session.execute(
            select(WeeklyChallenge).where(WeeklyChallenge.week_start == week_start)
        )).scalar_one_or_none()

        if existing:
            return existing

        template = random.choice(WEEKLY_POOL)
        wc = WeeklyChallenge(
            week_start=week_start,
            title=template["title"],
            description=template["description"],
            task_type=template["task_type"],
            target_value=template["target_value"],
            reward_points=template["reward_points"],
        )
        session.add(wc)
        await session.commit()
        await session.refresh(wc)

        logger.info(f"[WEEKLY] Created for {week_start.date()}: {wc.title}")
        return wc


async def get_user_weekly_challenge(user_id: int) -> dict:
    wc = await get_or_create_weekly_challenge()
    if wc is None:
        return {}

    async with async_session() as session:
        uc = (await session.execute(
            select(UserWeeklyChallenge).where(
                UserWeeklyChallenge.user_id == user_id,
                UserWeeklyChallenge.challenge_id == wc.id,
            )
        )).scalar_one_or_none()

        if uc is None:
            uc = UserWeeklyChallenge(
                user_id=user_id,
                challenge_id=wc.id,
                progress=0,
                status="in_progress",
            )
            session.add(uc)
            await session.commit()
            await session.refresh(uc)

        progress = uc.progress
        status = uc.status

    return {
        "challenge_id": wc.id,
        "title": wc.title,
        "description": wc.description,
        "task_type": wc.task_type,
        "target_value": wc.target_value,
        "reward_points": wc.reward_points,
        "progress": progress,
        "status": status,
    }


async def increment_weekly_progress(user_id: int, task_type: str, amount: int = 1) -> dict:
    wc = await get_or_create_weekly_challenge()
    if wc is None or wc.task_type != task_type:
        return {"matched": False, "completed": False, "reward_points": 0}

    async with async_session() as session:
        uc = (await session.execute(
            select(UserWeeklyChallenge).where(
                UserWeeklyChallenge.user_id == user_id,
                UserWeeklyChallenge.challenge_id == wc.id,
            )
        )).scalar_one_or_none()

        if uc is None:
            uc = UserWeeklyChallenge(
                user_id=user_id,
                challenge_id=wc.id,
                progress=0,
                status="in_progress",
            )
            session.add(uc)
            await session.flush()

        if uc.status == "completed":
            return {"matched": True, "completed": False, "reward_points": 0}

        uc.progress += amount

        completed = False
        if uc.progress >= wc.target_value:
            uc.status = "completed"
            uc.completed_at = datetime.now(timezone.utc)
            completed = True

        await session.commit()

    if completed:
        await add_custom_points(user_id, wc.reward_points)
        logger.info(
            f"[WEEKLY] user={user_id} completed '{wc.title}' +{wc.reward_points}"
        )

    return {
        "matched": True,
        "completed": completed,
        "reward_points": wc.reward_points,
    }