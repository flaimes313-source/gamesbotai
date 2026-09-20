"""
Коллекция архетипов.
"""
from typing import List, Optional

from sqlalchemy import select

from database.connection import async_session
from database.models import UserEngagement
from services.engagement.points import add_points
from utils.logging import get_logger

logger = get_logger(__name__)


# Максимум для коллекции (для прогресса)
MAX_ARCHETYPES = 20


async def add_archetype(user_id: int, archetype: str) -> bool:
    """
    Добавляет архетип в коллекцию.
    Возвращает True, если это новый архетип.
    """
    if not archetype:
        return False

    archetype = archetype.strip().upper()

    async with async_session() as session:
        eng = (await session.execute(
            select(UserEngagement).where(UserEngagement.user_id == user_id)
        )).scalar_one_or_none()

        if eng is None:
            eng = UserEngagement(
                user_id=user_id,
                archetypes_collected={},
                total_analyses=0,
            )
            session.add(eng)
            await session.flush()

        collected = eng.archetypes_collected or {}

        if archetype in collected:
            # Уже есть — обновляем счётчик
            collected[archetype] = collected[archetype] + 1
            eng.archetypes_collected = collected
            eng.total_analyses += 1
            await session.commit()
            return False

        # Новый архетип
        collected[archetype] = 1
        eng.archetypes_collected = collected
        eng.total_analyses += 1
        await session.commit()

    # Награда за новый
    await add_points(user_id, "new_archetype")
    logger.info(f"[ARCHETYPE] user={user_id} new='{archetype}'")
    return True


async def get_collection(user_id: int) -> dict:
    """Возвращает {archetype: count}."""
    async with async_session() as session:
        eng = (await session.execute(
            select(UserEngagement).where(UserEngagement.user_id == user_id)
        )).scalar_one_or_none()
        return dict(eng.archetypes_collected or {}) if eng else {}


async def get_collection_stats(user_id: int) -> dict:
    """Статистика по коллекции."""
    collection = await get_collection(user_id)
    unique = len(collection)
    total_analyses = sum(collection.values())

    return {
        "unique": unique,
        "total": total_analyses,
        "max": MAX_ARCHETYPES,
        "progress_pct": round(unique / MAX_ARCHETYPES * 100, 1) if MAX_ARCHETYPES else 0,
    }