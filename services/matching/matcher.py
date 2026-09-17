import random
from typing import Any, Dict, List, Optional

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Match, Profile, User
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
        "description": p.description,
        "funny_trait": p.funny_trait,
    }


async def get_my_profile(session: AsyncSession, user_id: int) -> Optional[Profile]:
    return (
        await session.execute(
            select(Profile).where(Profile.user_id == user_id).order_by(Profile.id.desc()).limit(1)
        )
    ).scalar_one_or_none()


async def get_my_user(session: AsyncSession, telegram_id: int) -> Optional[User]:
    return (await session.execute(select(User).where(User.telegram_id == telegram_id))).scalar_one_or_none()


async def get_user_by_id(session: AsyncSession, user_id: int) -> Optional[User]:
    return (await session.execute(select(User).where(User.id == user_id))).scalar_one_or_none()


async def _existing_match_ids(session: AsyncSession, me_id: int) -> set[int]:
    """Возвращаем id пользователей, с которыми уже есть match (любой статус)."""
    rows = (
        await session.execute(
            select(Match.user1_id, Match.user2_id).where(
                or_(Match.user1_id == me_id, Match.user2_id == me_id)
            )
        )
    ).all()
    ids: set[int] = set()
    for u1, u2 in rows:
        ids.add(u1 if u1 != me_id else u2)
    return ids


async def find_candidates(
    session: AsyncSession,
    me_user_id: int,
    mode: str = "similar",
    limit: int = 20,
    exclude_ids: Optional[set[int]] = None,
) -> List[Dict[str, Any]]:
    """
    Возвращает список кандидатов (без тех, с кем уже есть матч).
    exclude_ids — дополнительно исключаемые user.id (например, уже показанные).
    """
    my_profile = await get_my_profile(session, me_user_id)
    if my_profile is None:
        return []

    my_dict = _profile_to_dict(my_profile)

    # исключаем тех, с кем уже матч
    blocked_ids = await _existing_match_ids(session, me_user_id)
    if exclude_ids:
        blocked_ids |= exclude_ids

    stmt = (
        select(Profile, User)
        .join(User, User.id == Profile.user_id)
        .where(User.participates_in_game.is_(True))
        .where(User.is_blocked.is_(False))
        .where(User.id != me_user_id)
    )
    if blocked_ids:
        stmt = stmt.where(User.id.notin_(blocked_ids))

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
                "show_profile": user.show_profile,
                "show_photo": user.show_photo,
                "allow_messages": user.allow_messages,
                "profile": other,
                "score": score,
            }
        )

    results = _sort_by_mode(results, my_dict, mode)
    return results[:limit]


def _sort_by_mode(
    items: List[Dict[str, Any]], my: Dict[str, Any], mode: str
) -> List[Dict[str, Any]]:
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
        random.shuffle(items)
    return items


async def create_match_record(
    session: AsyncSession,
    me_id: int,
    other_id: int,
    match_type: str,
    score: int,
) -> Match:
    """Создаёт запись матча. Порядок user1_id < user2_id — чтобы UniqueConstraint работал."""
    u1, u2 = (me_id, other_id) if me_id < other_id else (other_id, me_id)

    existing = (
        await session.execute(
            select(Match).where(Match.user1_id == u1, Match.user2_id == u2)
        )
    ).scalar_one_or_none()

    if existing:
        existing.match_type = match_type
        existing.score = score
        await session.commit()
        await session.refresh(existing)
        return existing

    match = Match(user1_id=u1, user2_id=u2, match_type=match_type, score=score, status="new")
    session.add(match)
    await session.commit()
    await session.refresh(match)
    logger.info(f"Match created: {u1} <-> {u2} ({score}%)")
    return match


async def mark_match_status(session: AsyncSession, match_id: int, status: str) -> None:
    m = (await session.execute(select(Match).where(Match.id == match_id))).scalar_one_or_none()
    if m:
        m.status = status
        await session.commit()