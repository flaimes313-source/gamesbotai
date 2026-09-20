"""
Очки и уровни.
"""
from sqlalchemy import select

from database.connection import async_session
from database.models import UserEngagement
from utils.logging import get_logger

logger = get_logger(__name__)


# ============================================================
# Таблица уровней
# ============================================================
# (уровень, очки для достижения, титул)
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


# ============================================================
# Награды за действия
# ============================================================
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
    "streak_bonus": 1,  # × N дней
}


def level_for_points(points: int) -> int:
    """Определяет уровень по очкам."""
    level = 1
    for lvl, threshold, _title in LEVELS:
        if points >= threshold:
            level = lvl
        else:
            break
    return level


def title_for_level(level: int) -> str:
    """Титул уровня."""
    for lvl, _threshold, title in LEVELS:
        if lvl == level:
            return title
    return "Новичок"


def points_to_next_level(current_points: int, current_level: int) -> int:
    """Сколько очков до следующего уровня."""
    if current_level >= MAX_LEVEL:
        return 0
    for lvl, threshold, _title in LEVELS:
        if lvl == current_level + 1:
            return max(0, threshold - current_points)
    return 0


async def get_or_create_engagement(session, user_id: int) -> UserEngagement:
    """Возвращает или создаёт запись engagement."""
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

        level_up = eng.level > old_level
        result = (added, eng.total_points, level_up)

    logger.info(f"[POINTS] user={user_id} action={action} +{added} → total={result[1]} level={level_for_points(result[1])}")
    return result


async def get_engagement(user_id: int) -> UserEngagement | None:
    async with async_session() as session:
        return (await session.execute(
            select(UserEngagement).where(UserEngagement.user_id == user_id)
        )).scalar_one_or_none()