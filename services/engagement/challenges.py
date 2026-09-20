"""
Ежедневные челленджи.
"""
import random
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import select

from database.connection import async_session
from database.models import DailyChallenge, UserChallenge, UserEngagement
from services.engagement.points import add_points
from utils.logging import get_logger

logger = get_logger(__name__)


# Пул заданий
CHALLENGE_POOL = [
    {
        "title": "Свежий взгляд",
        "description": "Отправь фото на AI-анализ — узнай свой архетип",
        "task_type": "photo",
        "target_value": 1,
        "reward_points": 50,
    },
    {
        "title": "Проверка мозгов",
        "description": "Пройди любой тест",
        "task_type": "test",
        "target_value": 1,
        "reward_points": 40,
    },
    {
        "title": "Общительный",
        "description": "Отправь 3 сообщения в чате другому игроку",
        "task_type": "message",
        "target_value": 3,
        "reward_points": 60,
    },
    {
        "title": "Приведи друга",
        "description": "Пригласи друга в бот по своей ссылке",
        "task_type": "invite",
        "target_value": 1,
        "reward_points": 100,
    },
    {
        "title": "Поделись вайбом",
        "description": "Поделись своей карточкой с друзьями",
        "task_type": "share",
        "target_value": 1,
        "reward_points": 40,
    },
    {
        "title": "Сравнение",
        "description": "Сравни свой профиль с другим игроком",
        "task_type": "compare",
        "target_value": 1,
        "reward_points": 50,
    },
    {
        "title": "Двойной анализ",
        "description": "Сделай 2 AI-анализа за день",
        "task_type": "analysis",
        "target_value": 2,
        "reward_points": 70,
    },
]


async def _get_today_start() -> datetime:
    """Начало сегодняшнего дня в UTC."""
    now = datetime.now(timezone.utc)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


async def get_or_create_today_challenge() -> Optional[DailyChallenge]:
    """
    Возвращает задание на сегодня. Создаёт, если нет.
    Использует существующий челлендж, если уже создан.
    """
    today = await _get_today_start()

    async with async_session() as session:
        existing = (await session.execute(
            select(DailyChallenge).where(DailyChallenge.date == today)
        )).scalar_one_or_none()

        if existing:
            return existing

        # Создаём новое задание
        template = random.choice(CHALLENGE_POOL)

        challenge = DailyChallenge(
            date=today,
            title=template["title"],
            description=template["description"],
            task_type=template["task_type"],
            target_value=template["target_value"],
            reward_points=template["reward_points"],
        )
        session.add(challenge)
        await session.commit()
        await session.refresh(challenge)

        logger.info(f"[CHALLENGE] Created for {today.date()}: {challenge.title}")
        return challenge


async def get_user_challenge(user_id: int) -> dict:
    """
    Возвращает прогресс по сегодняшнему челленджу.
    """
    challenge = await get_or_create_today_challenge()
    if challenge is None:
        return {}

    async with async_session() as session:
        uc = (await session.execute(
            select(UserChallenge).where(
                UserChallenge.user_id == user_id,
                UserChallenge.challenge_id == challenge.id,
            )
        )).scalar_one_or_none()

        if uc is None:
            uc = UserChallenge(
                user_id=user_id,
                challenge_id=challenge.id,
                progress=0,
                status="in_progress",
            )
            session.add(uc)
            await session.commit()
            await session.refresh(uc)

    return {
        "challenge_id": challenge.id,
        "title": challenge.title,
        "description": challenge.description,
        "task_type": challenge.task_type,
        "target_value": challenge.target_value,
        "reward_points": challenge.reward_points,
        "progress": uc.progress,
        "status": uc.status,
    }


async def increment_progress(user_id: int, task_type: str, amount: int = 1) -> dict:
    """
    Увеличивает прогресс юзера в челлендже дня, если тип совпал.
    Возвращает:
        {"matched": bool, "completed": bool, "reward_points": int}
    """
    challenge = await get_or_create_today_challenge()
    if challenge is None or challenge.task_type != task_type:
        return {"matched": False, "completed": False, "reward_points": 0}

    async with async_session() as session:
        uc = (await session.execute(
            select(UserChallenge).where(
                UserChallenge.user_id == user_id,
                UserChallenge.challenge_id == challenge.id,
            )
        )).scalar_one_or_none()

        if uc is None:
            uc = UserChallenge(
                user_id=user_id,
                challenge_id=challenge.id,
                progress=0,
                status="in_progress",
            )
            session.add(uc)
            await session.flush()

        if uc.status == "completed":
            return {"matched": True, "completed": False, "reward_points": 0}

        uc.progress += amount

        completed = False
        if uc.progress >= challenge.target_value:
            uc.status = "completed"
            uc.completed_at = datetime.now(timezone.utc)
            completed = True

        await session.commit()

    if completed:
        # Начисляем очки
        await add_points(user_id, "challenge_complete")
        logger.info(f"[CHALLENGE] user={user_id} completed '{challenge.title}'")

    return {
        "matched": True,
        "completed": completed,
        "reward_points": challenge.reward_points if completed else 0,
    }