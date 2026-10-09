"""
«Сравнение 2 фото» (Этап D).

Логика:
1. Проверка лимита: Free — 1 раз/день, Pro — безлимит.
2. Сбор данных профиля.
3. AI: сравнить два фото.
4. Free: базовое сравнение + интрига.
5. Pro: полный разбор.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import select

from database.connection import async_session
from database.models import Profile, RewardClaim, User
from services.ai.factory import get_ai_provider
from services.premium import is_premium
from utils.logging import get_logger

logger = get_logger(__name__)


FREE_DAILY_LIMIT = 1


def _today_code() -> str:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return f"photo_battle_{today}"


async def _check_limit(user_id: int, telegram_id: int) -> tuple[bool, bool]:
    is_pro = await is_premium(telegram_id)
    if is_pro:
        return True, True

    code = _today_code()
    async with async_session() as session:
        existing = (await session.execute(
            select(RewardClaim).where(
                RewardClaim.user_id == user_id,
                RewardClaim.reward_code == code,
            )
        )).scalar_one_or_none()

    return (existing is None), False


async def _mark_used(user_id: int) -> None:
    code = _today_code()
    try:
        async with async_session() as session:
            session.add(RewardClaim(
                user_id=user_id,
                reward_code=code,
                payload={"type": "photo_battle"},
            ))
            await session.commit()
    except Exception:
        pass


async def _collect_profile_data(user_id: int) -> Optional[Dict[str, Any]]:
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

        return {
            "user_name": user.first_name or "Игрок",
            "archetype": profile.archetype if profile else "",
        }


async def generate_photo_battle_for_user(
    user_id: int,
    telegram_id: int,
    image_1_bytes: bytes,
    image_2_bytes: bytes,
) -> Optional[Dict[str, Any]]:
    allowed, is_pro = await _check_limit(user_id, telegram_id)
    if not allowed:
        return {
            "allowed": False,
            "reason": "limit_reached",
            "is_pro": False,
        }

    data = await _collect_profile_data(user_id)
    if data is None:
        return {
            "allowed": False,
            "reason": "no_profile",
            "is_pro": is_pro,
        }

    try:
        provider = await get_ai_provider()
        result = await provider.generate_photo_battle(
            image_1_bytes=image_1_bytes,
            image_2_bytes=image_2_bytes,
            profile_data=data,
        )
    except Exception:
        logger.exception("[PHOTO_BATTLE] AI failed")
        return {
            "allowed": False,
            "reason": "ai_failed",
            "is_pro": is_pro,
        }

    # Лимит тратится ТОЛЬКО если AI сработал
    if not is_pro:
        await _mark_used(user_id)

    return {
        "allowed": True,
        "reason": "ok",
        "is_pro": is_pro,
        "score_1": int(result.get("score_1", 0)),
        "score_2": int(result.get("score_2", 0)),
        "winner": int(result.get("winner", 1)),
        "short_reason": result.get("short_reason", ""),
        "why_winner": result.get("why_winner", ""),
        "why_loser": result.get("why_loser", ""),
        "best_for": result.get("best_for", ""),
    }


def format_photo_battle(result: Dict[str, Any]) -> str:
    if not result.get("allowed"):
        reason = result.get("reason")
        if reason == "limit_reached":
            return (
                "⚔️ <b>Сравнение 2 фото</b>\n\n"
                "Ты уже использовал бесплатное сравнение на сегодня.\n\n"
                "💎 <b>С Pro — безлимит.</b>"
            )
        if reason == "no_profile":
            return (
                "⚔️ <b>Сравнение 2 фото</b>\n\n"
                "Сначала отправь фото — я должен знать твой вайб."
            )
        if reason == "ai_failed":
            return (
                "😔 <b>AI сейчас перегружен</b>\n\n"
                "GigaChat временно не отвечает — попробуй через минуту.\n\n"
                "🔁 <b>Лимит Free не потрачен.</b>"
            )
        return "😔 Не получилось. Попробуй позже."

    score_1 = result.get("score_1", 0)
    score_2 = result.get("score_2", 0)
    winner = result.get("winner", 1)

    medal_1 = "🏆" if winner == 1 else "🥈"
    medal_2 = "🏆" if winner == 2 else "🥈"

    text = (
        f"⚔️ <b>БИТВА ВАЙБОВ</b>\n\n"
        f"{medal_1} Фото №1 — <b>{score_1}</b>/100\n"
        f"{medal_2} Фото №2 — <b>{score_2}</b>/100\n\n"
        f"🏆 <b>Победитель: Фото №{winner}</b>\n\n"
        f"<i>{result.get('short_reason', '')}</i>\n"
    )

    if result.get("is_pro"):
        text += "\n✨ <b>Полный разбор (PRO)</b>\n\n"

        why_winner = result.get("why_winner", "")
        if why_winner:
            text += f"🏆 <b>Почему победитель сильнее:</b>\n{why_winner}\n\n"

        why_loser = result.get("why_loser", "")
        if why_loser:
            text += f"📉 <b>Что слабее у второго фото:</b>\n{why_loser}\n\n"

        best_for = result.get("best_for", "")
        if best_for:
            text += f"💡 <b>Для чего лучше подойдёт:</b>\n{best_for}\n"
    else:
        text += (
            "\n💎 <b>Хочешь полный разбор?</b>\n"
            "• Почему победитель выглядит увереннее\n"
            "• Что привлекает внимание\n"
            "• Что делает второе фото слабее\n"
            "• Какое лучше для знакомств\n\n"
            "👇 Жми, чтобы узнать"
        )

    return text