from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Profile, User
from services.matching.compatibility import compatibility_score
from utils.logging import get_logger

logger = get_logger(__name__)


def _profile_to_dict(p: Profile) -> Dict[str, Any]:
    return {
        "archetype": p.archetype,
        "charisma": p.charisma,
        "confidence": p.confidence,
        "humor": p.humor,
        "energy": p.energy,
        "sociability": p.sociability,
        "intellect": p.intellect,
        "creativity": p.creativity,
        "calmness": p.calmness,
        "chaos": p.chaos,
        "leadership": p.leadership,
        "danger_level": p.danger_level,
        "friendship_score": p.friendship_score,
        "vibe": p.vibe,
    }


async def find_candidates(
    session: AsyncSession,
    me_user_id: int,
    mode: str = "similar",
    limit: int = 20,
) -> List[Dict[str, Any]]:
    my_profile = (
        await session.execute(
            select(Profile).where(Profile.user_id == me_user_id).order_by(Profile.id.desc()).limit(1)
        )
    ).scalar_one_or_none()

    if my_profile is None:
        return []

    my_dict = _profile_to_dict(my_profile)

    stmt = (
        select(Profile, User)
        .join(User, User.id == Profile.user_id)
        .where(User.participates_in_game.is_(True))
        .where(User.is_blocked.is_(False))
        .where(User.id != me_user_id)
    )
    rows = (await session.execute(stmt)).all()

    results: List[Dict[str, Any]] = []
    for profile, user in rows:
        other = _profile_to_dict(profile)
        score = compatibility_score(my_dict, other)
        results.append(
            {
                "user_id": user.id,
                "telegram_id": user.telegram_id,
                "username": user.username,
                "first_name": user.first_name,
                "show_username": user.show_username,
                "profile": other,
                "score": score,
            }
        )

    results = _sort_by_mode(results, my_dict, mode)
    return results[:limit]


def _sort_by_mode(items: List[Dict[str, Any]], my: Dict[str, Any], mode: str) -> List[Dict[str, Any]]:
    if mode == "similar":
        items.sort(key=lambda x: x["score"], reverse=True)
    elif mode == "opposite":
        items.sort(key=lambda x: x["score"])
    elif mode == "funny":
        items.sort(key=lambda x: x["profile"]["humor"], reverse=True)
    elif mode == "charismatic":
        items.sort(key=lambda x: x["profile"]["charisma"], reverse=True)
    elif mode == "intellectual":
        items.sort(key=lambda x: x["profile"]["intellect"], reverse=True)
    elif mode == "chaos":
        items.sort(key=lambda x: x["profile"]["chaos"], reverse=True)
    else:  # random
        import random

        random.shuffle(items)
    return items