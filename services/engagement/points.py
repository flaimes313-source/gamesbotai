"""
Очки и уровни.
"""
from typing import Optional

from sqlalchemy import select

from database.connection import async_session
from database.models import UserEngagement
from utils.logging import get_logger

logger = get_logger(__name__)


LEVELS = [
    (1, 0, "Новичок"),
    (2, 50, "Наблюдатель"),
    (3, 150, "Участник"),
    (4, 300, "Завсегдатай"),
    (5, 500, "Постоянный"),
    (6, 800, "Активист"),
    (7, 1200, "Ветеран"),
    (8, 1800, "Опытный"),
    (9, 2600, "Мастер вайба"),
    (10, 3600, "Гуру вайба"),
    (11, 5000, "Легенда"),
    (12, 7000, "Миф"),
    (13, 9500, "Хранитель"),
    (14, 12500, "Владыка хаоса"),
    (15, 16000, "Архитектор вайбов"),
    (16, 20000, "Творец"),
    (17, 25000, "Создатель"),
    (18, 32000, "Полубог"),
    (19, 42000, "Бог вайба"),
    (20, 55000, "ЛЕГЕНДА ВАЙБМИ"),
]

MAX_LEVEL = 20


LEVEL_ACHIEVEMENTS = {
    5: "level_5",
    10: "level_10",
    15: "level_15",
    20: "level_20",
}


POINTS = {
    "daily_login": 5,
    "first_login": 10,
    "photo_analysis": 15,
    "new_archetype": 30,
    "test_complete": 20,
    "first_message": 10,
    "share": 5,
    "invite_friend": 50,
    "challenge_complete": 50,
    "streak_bonus": 1,
}


def level_for_points(points: int) -> int:
    level = 1
    for lvl, threshold, _title in LEVELS:
        if points >= threshold:
            level = lvl
        else:
            break
    return level


def title_for_level(level: int) -> str:
    for lvl, _threshold, title in LEVELS:
        if lvl == level:
            return title
    return "Новичок"


def points_to_next_level(current_points: int, current_level: int) -> int:
    if current_level >= MAX_LEVEL:
        return 0
    for lvl, threshold, _title in LEVELS:
        if lvl == current_level + 1:
            return max(0, threshold - current_points)
    return 0


async def get_or_create_engagement(session, user_id: int) -> UserEngagement:
    row = (await session.execute(
        select(UserEngagement).where(UserEngagement.user_id == user_id)
    )).scalar_one_or_none()

    if row is None:
        row = UserEngagement(user_id=user_id)
        session.add(row)
        await session.flush()

    return row


async def add_points(user_id: int, action: str, multiplier: int = 1) -> tuple[int, int, bool]:
    """
    Начисляет очки за действие.
    Возвращает: (added, total_points, level_up)
    """
    base = POINTS.get(action, 0)
    if base == 0:
        return 0, 0, False

    added = base * multiplier

    async with async_session() as session:
        eng = await get_or_create_engagement(session, user_id)
        old_level = eng.level

        eng.total_points += added
        eng.level = level_for_points(eng.total_points)

        await session.commit()

        new_level = eng.level
        total_points = eng.total_points

    level_up = new_level > old_level

    if level_up:
        logger.info(f"[POINTS] user={user_id} LEVEL UP {old_level} → {new_level}")
        await _on_level_up(user_id, old_level, new_level)

    # Проверка наград за очки
    try:
        from services.engagement.points_rewards import check_points_rewards
        await check_points_rewards(user_id, total_points)
    except Exception:
        logger.exception("[POINTS] check_points_rewards failed")

    logger.info(
        f"[POINTS] user={user_id} action={action} +{added} → "
        f"total={total_points} level={new_level}"
    )
    return added, total_points, level_up


async def _on_level_up(user_id: int, old_level: int, new_level: int) -> None:
    """Обработка повышения уровня — достижения + уведомление."""
    try:
        from services.achievements import unlock_achievement
    except Exception:
        logger.exception("[POINTS] Cannot import achievements")
        return

    for milestone, code in LEVEL_ACHIEVEMENTS.items():
        if old_level < milestone <= new_level:
            try:
                await unlock_achievement(user_id, code)
            except Exception:
                logger.exception(f"[POINTS] Failed to unlock {code}")

    try:
        from database.models import User
        from services.engagement.notifications import add_level_up_notification

        async with async_session() as session:
            user = (await session.execute(
                select(User).where(User.id == user_id)
            )).scalar_one_or_none()

        if user:
            eng = await get_engagement(user_id)
            if eng:
                title = title_for_level(new_level)
                to_next = points_to_next_level(eng.total_points, new_level)
                add_level_up_notification(
                    user.telegram_id,
                    level=new_level,
                    title=title,
                    total_points=eng.total_points,
                    to_next=to_next,
                )
    except Exception:
        logger.exception("[POINTS] Failed to queue level up notification")


async def get_engagement(user_id: int) -> Optional[UserEngagement]:
    async with async_session() as session:
        return (await session.execute(
            select(UserEngagement).where(UserEngagement.user_id == user_id)
        )).scalar_one_or_none()