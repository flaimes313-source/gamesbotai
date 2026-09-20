"""
Главный API вовлечения.
"""
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


__all__ = [
    "add_points", "add_archetype", "get_collection", "get_collection_stats",
    "get_or_create_today_challenge", "get_user_challenge", "increment_progress",
    "get_engagement", "level_for_points", "title_for_level", "points_to_next_level",
    "update_streak", "get_streak",
    "on_user_visit", "on_photo_analyzed", "on_test_completed",
    "on_message_sent", "on_share", "on_compare",
    "LEVELS", "MAX_LEVEL", "POINTS",
]


async def on_user_visit(user_id: int) -> dict:
    return await update_streak(user_id)


async def on_photo_analyzed(user_id: int, archetype: str) -> dict:
    is_new = await add_archetype(user_id, archetype)
    await add_points(user_id, "photo_analysis")

    challenge_result = await increment_progress(user_id, "photo")
    if not challenge_result.get("matched"):
        await increment_progress(user_id, "analysis")

    # Weekly
    try:
        from services.engagement.weekly_challenges import increment_weekly_progress
        await increment_weekly_progress(user_id, "photo")
    except Exception:
        logger.exception("Weekly increment failed")

    # Quests
    try:
        from services.engagement.quests import advance_quest
        await advance_quest(user_id, "photo")
    except Exception:
        logger.exception("Quest advance failed")

    return {
        "is_new_archetype": is_new,
        "challenge": challenge_result,
    }


async def on_test_completed(user_id: int) -> dict:
    await add_points(user_id, "test_complete")
    result = await increment_progress(user_id, "test")

    try:
        from services.engagement.weekly_challenges import increment_weekly_progress
        await increment_weekly_progress(user_id, "test")
    except Exception:
        logger.exception("Weekly increment failed")

    try:
        from services.engagement.quests import advance_quest
        await advance_quest(user_id, "test")
    except Exception:
        logger.exception("Quest advance failed")

    return result


async def on_message_sent(user_id: int) -> dict:
    await add_points(user_id, "first_message")
    result = await increment_progress(user_id, "message")

    try:
        from services.engagement.weekly_challenges import increment_weekly_progress
        await increment_weekly_progress(user_id, "message")
    except Exception:
        logger.exception("Weekly increment failed")

    try:
        from services.engagement.quests import advance_quest
        await advance_quest(user_id, "message")
    except Exception:
        logger.exception("Quest advance failed")

    return result


async def on_share(user_id: int) -> dict:
    await add_points(user_id, "share")
    result = await increment_progress(user_id, "share")

    try:
        from services.engagement.quests import advance_quest
        await advance_quest(user_id, "share")
    except Exception:
        logger.exception("Quest advance failed")

    return result


async def on_compare(user_id: int) -> dict:
    result = await increment_progress(user_id, "compare")

    try:
        from services.engagement.weekly_challenges import increment_weekly_progress
        await increment_weekly_progress(user_id, "compare")
    except Exception:
        logger.exception("Weekly increment failed")

    try:
        from services.engagement.quests import advance_quest
        await advance_quest(user_id, "compare")
    except Exception:
        logger.exception("Quest advance failed")

    return result


async def on_search(user_id: int) -> None:
    """Вызывается при поиске игроков."""
    try:
        from services.engagement.quests import advance_quest
        await advance_quest(user_id, "search")
    except Exception:
        logger.exception("Quest advance failed")