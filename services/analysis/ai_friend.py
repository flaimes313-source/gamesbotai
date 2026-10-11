"""
«AI-друг» (Этап F).

Логика:
1. Проверка лимита: Free — 3 сообщения/день, Pro — безлимит.
2. Загрузка истории из БД (последние 10 сообщений для AI).
3. Сбор Vibe-профиля юзера.
4. AI → ответ в роли друга.
5. Сохранение user-сообщения и ответа в БД.
6. Лимит тратится только после успешного ответа.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import delete, func, select

from database.connection import async_session
from database.models import AIFriendMessage, Profile, RewardClaim, User
from services.ai.factory import get_ai_provider
from services.premium import is_premium
from utils.logging import get_logger

logger = get_logger(__name__)


FREE_DAILY_LIMIT = 3
HISTORY_FOR_AI = 10
HISTORY_IN_DB_MAX = 50
RETENTION_DAYS = 30
HISTORY_FOR_VIEW = 20


def _today_code() -> str:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return f"ai_friend_{today}"


# ============================================================
# ЛИМИТ
# ============================================================
async def _get_used_today(user_id: int) -> int:
    code = _today_code()
    async with async_session() as session:
        cnt = (await session.execute(
            select(func.count(RewardClaim.id))
            .where(RewardClaim.user_id == user_id)
            .where(RewardClaim.reward_code.like(f"{code}_%"))
        )).scalar_one()
    return int(cnt or 0)


async def _mark_used(user_id: int) -> None:
    code = _today_code()
    stamp = datetime.now(timezone.utc).strftime("%H%M%S%f")
    try:
        async with async_session() as session:
            session.add(RewardClaim(
                user_id=user_id,
                reward_code=f"{code}_{stamp}",
                payload={"type": "ai_friend"},
            ))
            await session.commit()
    except Exception:
        logger.exception("[AI_FRIEND] _mark_used failed")


async def check_ai_friend_limit(
    user_id: int,
    telegram_id: int,
) -> tuple[bool, bool, int]:
    """Возвращает (allowed, is_pro, remaining). remaining = -1 для Pro."""
    is_pro = await is_premium(telegram_id)
    if is_pro:
        return True, True, -1

    used = await _get_used_today(user_id)
    remaining = max(0, FREE_DAILY_LIMIT - used)
    return (remaining > 0), False, remaining


# ============================================================
# ИСТОРИЯ — для AI
# ============================================================
async def load_history(user_id: int, limit: int = HISTORY_FOR_AI) -> List[Dict[str, str]]:
    async with async_session() as session:
        rows = (await session.execute(
            select(AIFriendMessage)
            .where(AIFriendMessage.user_id == user_id)
            .order_by(AIFriendMessage.id.desc())
            .limit(limit)
        )).scalars().all()

    rows = list(reversed(rows))
    return [{"role": r.role, "text": r.text} for r in rows]


# ============================================================
# ИСТОРИЯ — для показа юзеру
# ============================================================
async def load_recent_messages(
    user_id: int,
    limit: int = HISTORY_FOR_VIEW,
) -> Dict[str, Any]:
    async with async_session() as session:
        total = (await session.execute(
            select(func.count(AIFriendMessage.id))
            .where(AIFriendMessage.user_id == user_id)
        )).scalar_one()

        rows = (await session.execute(
            select(AIFriendMessage)
            .where(AIFriendMessage.user_id == user_id)
            .order_by(AIFriendMessage.id.desc())
            .limit(limit)
        )).scalars().all()

    rows = list(reversed(rows))
    messages = [{"role": r.role, "text": r.text} for r in rows]

    return {
        "messages": messages,
        "total": int(total or 0),
        "shown": len(messages),
    }


# ============================================================
# СОХРАНЕНИЕ / ОЧИСТКА
# ============================================================
async def save_message(user_id: int, role: str, text: str) -> None:
    if not text:
        return
    try:
        async with async_session() as session:
            session.add(AIFriendMessage(
                user_id=user_id,
                role=role,
                text=text[:4000],
            ))
            await session.commit()
    except Exception:
        logger.exception("[AI_FRIEND] save_message failed")


async def trim_history(user_id: int) -> None:
    try:
        async with async_session() as session:
            rows = (await session.execute(
                select(AIFriendMessage.id)
                .where(AIFriendMessage.user_id == user_id)
                .order_by(AIFriendMessage.id.desc())
                .limit(HISTORY_IN_DB_MAX)
            )).scalars().all()

            if len(rows) < HISTORY_IN_DB_MAX:
                return

            threshold_id = rows[-1]

            await session.execute(
                delete(AIFriendMessage)
                .where(AIFriendMessage.user_id == user_id)
                .where(AIFriendMessage.id < threshold_id)
            )
            await session.commit()
    except Exception:
        logger.exception("[AI_FRIEND] trim_history failed")


async def clear_history(user_id: int) -> int:
    try:
        async with async_session() as session:
            res = await session.execute(
                delete(AIFriendMessage).where(AIFriendMessage.user_id == user_id)
            )
            await session.commit()
            return int(res.rowcount or 0)
    except Exception:
        logger.exception("[AI_FRIEND] clear_history failed")
        return 0


async def count_history(user_id: int) -> int:
    async with async_session() as session:
        cnt = (await session.execute(
            select(func.count(AIFriendMessage.id))
            .where(AIFriendMessage.user_id == user_id)
        )).scalar_one()
    return int(cnt or 0)


# ============================================================
# ПРОФИЛЬ
# ============================================================
async def collect_profile_data(user_id: int) -> Optional[Dict[str, Any]]:
    async with async_session() as session:
        user = (await session.execute(
            select(User).where(User.id == user_id)
        )).scalar_one_or_none()
        if user is None:
            return None

        profile = (await session.execute(
            select(Profile)
            .where(Profile.user_id == user_id)
            .order_by(Profile.id.desc())
            .limit(1)
        )).scalar_one_or_none()

        recent_rows = (await session.execute(
            select(Profile.archetype)
            .where(Profile.user_id == user_id)
            .order_by(Profile.id.desc())
            .limit(3)
        )).scalars().all()

        return {
            "user_name": user.first_name or "Игрок",
            "archetype": profile.archetype if profile else "",
            "vibe": (profile.vibe or "") if profile else "",
            "charisma": profile.charisma if profile else 0,
            "confidence": profile.confidence if profile else 0,
            "humor": profile.humor if profile else 0,
            "energy": profile.energy if profile else 0,
            "sociability": profile.sociability if profile else 0,
            "chaos": profile.chaos if profile else 0,
            "recent_archetypes": [a for a in recent_rows if a],
        }


# ============================================================
# ОСНОВНАЯ ФУНКЦИЯ
# ============================================================
async def generate_ai_friend_reply(
    user_id: int,
    telegram_id: int,
    user_message: str,
) -> Dict[str, Any]:
    """
    Возвращает:
        {
            "allowed": bool,
            "reason": str,
            "is_pro": bool,
            "reply": str,
            "remaining": int,
        }
    """
    allowed, is_pro, remaining = await check_ai_friend_limit(user_id, telegram_id)
    if not allowed:
        return {
            "allowed": False,
            "reason": "limit_reached",
            "is_pro": False,
            "reply": "",
            "remaining": 0,
        }

    data = await collect_profile_data(user_id)
    if data is None:
        return {
            "allowed": False,
            "reason": "no_profile",
            "is_pro": is_pro,
            "reply": "",
            "remaining": remaining,
        }

    history = await load_history(user_id, limit=HISTORY_FOR_AI)

    try:
        provider = await get_ai_provider()
        reply = await provider.generate_ai_friend_reply(
            profile_data=data,
            history=history,
            user_message=user_message,
        )
    except Exception:
        logger.exception("[AI_FRIEND] AI failed")
        return {
            "allowed": False,
            "reason": "ai_failed",
            "is_pro": is_pro,
            "reply": "",
            "remaining": remaining,
        }

    await save_message(user_id, "user", user_message)
    await save_message(user_id, "assistant", reply)
    await trim_history(user_id)

    if not is_pro:
        await _mark_used(user_id)
        remaining = max(0, remaining - 1)

    return {
        "allowed": True,
        "reason": "ok",
        "is_pro": is_pro,
        "reply": reply,
        "remaining": remaining,
    }


# ============================================================
# ФОРМАТИРОВАНИЕ ИСТОРИИ ДЛЯ ПОКАЗА
# ============================================================
def format_history_for_view(history_data: Dict[str, Any]) -> str:
    total = history_data.get("total", 0)
    shown = history_data.get("shown", 0)
    messages = history_data.get("messages", [])

    if total == 0:
        return (
            "📜 <b>ИСТОРИЯ AI-ДРУГА</b>\n\n"
            "<i>Пока пусто. Напиши что-нибудь — начнём.</i>"
        )

    def esc(s: str) -> str:
        return (
            s.replace("&", "&amp;")
             .replace("<", "&lt;")
             .replace(">", "&gt;")
        )

    lines = [
        "📜 <b>ИСТОРИЯ AI-ДРУГА</b>",
        "",
    ]

    if total > shown:
        lines.append(f"Всего сообщений: <b>{total}</b>")
        lines.append(f"Показаны последние <b>{shown}</b>:")
    else:
        lines.append(f"Всего сообщений: <b>{total}</b>")

    lines.append("")

    for m in messages:
        role = m.get("role")
        text = esc((m.get("text") or "").strip())

        if len(text) > 400:
            text = text[:400] + "…"

        if role == "user":
            lines.append("👤 <b>Ты:</b>")
            lines.append(text)
        else:
            lines.append("🤖 <b>AI:</b>")
            lines.append(text)

        lines.append("───────────────────")

    result = "\n".join(lines)

    if len(result) > 4000:
        result = result[:3990] + "\n…\n<i>(обрезано)</i>"

    return result