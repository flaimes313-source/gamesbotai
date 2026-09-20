"""
Главный API вовлечения.
Все вызовы из хендлеров — только через этот модуль.
"""
from typing import Optional

from services.engagement.archetypes import (
    add_archetype,
    get_collection,
    get_collection_stats,
)
from services.engagement.challenges import (
    get_or_create_today_challenge,
    get_user_challenge,
    increment_progress,
)
from services.engagement.points import (
    LEVELS,
    MAX_LEVEL,
    POINTS,
    add_points,
    get_engagement,
    level_for_points,
    points_to_next_level,
    title_for_level,
)
from services.engagement.streaks import get_streak, update_streak
from utils.logging import get_logger

logger = get_logger(__name__)


# ============================================================
# Экспорт
# ============================================================
__all__ = [
    "add_points",
    "add_archetype",
    "get_collection",
    "get_collection_stats",
    "get_or_create_today_challenge",
    "get_user_challenge",
    "increment_progress",
    "get_engagement",
    "level_for_points",
    "title_for_level",
    "points_to_next_level",
    "update_streak",
    "get_streak",
    "LEVELS",
    "MAX_LEVEL",
    "POINTS",
]


# ============================================================
# Обёртки для типовых действий
# ============================================================
async def on_user_visit(user_id: int) -> dict:
    """Вызывается при /start или первом действии дня."""
    return await update_streak(user_id)


async def on_photo_analyzed(user_id: int, archetype: str) -> dict:
    """Вызывается после анализа фото."""
    is_new = await add_archetype(user_id, archetype)

    # Очки за анализ
    await add_points(user_id, "photo_analysis")

    # Прогресс по челленджу
    challenge_result = await increment_progress(user_id, "photo")
    if not challenge_result.get("matched"):
        # Попробуем "analysis" (для задания «2 анализа»)
        await increment_progress(user_id, "analysis")

    return {
        "is_new_archetype": is_new,
        "challenge": challenge_result,
    }


async def on_test_completed(user_id: int) -> dict:
    await add_points(user_id, "test_complete")
    return await increment_progress(user_id, "test")


async def on_message_sent(user_id: int) -> dict:
    await add_points(user_id, "first_message")
    return await increment_progress(user_id, "message")


async def on_share(user_id: int) -> dict:
    await add_points(user_id, "share")
    return await increment_progress(user_id, "share")


async def on_referral(user_id: int) -> dict:
    await add_points(user_id, "invite_friend")
    return await increment_progress(user_id, "invite")


async def on_compare(user_id: int) -> dict:
    return await increment_progress(user_id, "compare")