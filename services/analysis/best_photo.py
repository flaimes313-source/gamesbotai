"""
«Выбрать лучшее фото» (Этап E).

Логика:
1. Проверка лимита: Free — 1 раз/день, Pro — безлимит.
2. Сбор данных профиля.
3. AI: сравнить 3 фото и выбрать лучшее.
4. Free: победитель + short_reason.
5. Pro: + разбор + разбивка по целям.
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
    return f"best_photo_{today}"


async def _check_limit(user_id: int, telegram_id: int) -> tuple[bool, bool]:
    """Возвращает (allowed, is_pro)."""
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
                payload={"type": "best_photo"},
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


async def generate_best_photo_for_user(
    user_id: int,
    telegram_id: int,
    image_1_bytes: bytes,
    image_2_bytes: bytes,
    image_3_bytes: bytes,
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
        result = await provider.generate_best_photo(
            image_1_bytes=image_1_bytes,
            image_2_bytes=image_2_bytes,
            image_3_bytes=image_3_bytes,
            profile_data=data,
        )
    except Exception:
        logger.exception("[BEST_PHOTO] AI failed")
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
        "score_3": int(result.get("score_3", 0)),
        "winner": int(result.get("winner", 1)),
        "short_reason": result.get("short_reason", ""),
        "why_winner": result.get("why_winner", ""),
        "why_others": result.get("why_others", ""),
        "best_for_telegram": int(result.get("best_for_telegram", 1)),
        "best_for_dating": int(result.get("best_for_dating", 1)),
        "best_for_business": int(result.get("best_for_business", 1)),
    }


def _medal(idx: int, winner: int) -> str:
    if idx == winner:
        return "🏆"
    return "•"


def format_best_photo(result: Dict[str, Any]) -> str:
    if not result.get("allowed"):
        reason = result.get("reason")
        if reason == "limit_reached":
            return (
                "🏆 <b>Выбрать лучшее фото</b>\n\n"
                "Ты уже использовал бесплатный выбор на сегодня.\n\n"
                "💎 <b>С Pro — безлимит.</b>"
            )
        if reason == "no_profile":
            return (
                "🏆 <b>Выбрать лучшее фото</b>\n\n"
                "Сначала отправь фото — я должен знать твой вайб."
            )
        if reason == "ai_failed":
            return (
                "😔 <b>AI сейчас перегружен</b>\n\n"
                "GigaChat временно не отвечает — попробуй через минуту.\n\n"
                "🔁 <b>Лимит Free не потрачен.</b>"
            )
        return "😔 Не получилось. Попробуй позже."

    s1 = result.get("score_1", 0)
    s2 = result.get("score_2", 0)
    s3 = result.get("score_3", 0)
    winner = result.get("winner", 1)

    m1 = _medal(1, winner)
    m2 = _medal(2, winner)
    m3 = _medal(3, winner)

    text = (
        f"🏆 <b>БИТВА ФОТО</b>\n\n"
        f"{m1} Фото №1 — <b>{s1}</b>/100\n"
        f"{m2} Фото №2 — <b>{s2}</b>/100\n"
        f"{m3} Фото №3 — <b>{s3}</b>/100\n\n"
        f"🏆 <b>Победитель: Фото №{winner}</b>\n\n"
        f"<i>{result.get('short_reason', '')}</i>\n"
    )

    if result.get("is_pro"):
        text += "\n✨ <b>Полный разбор (PRO)</b>\n\n"

        why_winner = result.get("why_winner", "")
        if why_winner:
            text += f"🏆 <b>Почему победитель сильнее:</b>\n{why_winner}\n\n"

        why_others = result.get("why_others", "")
        if why_others:
            text += f"📉 <b>Что слабее у остальных:</b>\n{why_others}\n\n"

        bft = result.get("best_for_telegram", 1)
        bfd = result.get("best_for_dating", 1)
        bfb = result.get("best_for_business", 1)
        text += (
            "🎯 <b>Какое фото для чего:</b>\n"
            f"• Telegram-аватарка — <b>№{bft}</b>\n"
            f"• Знакомства — <b>№{bfd}</b>\n"
            f"• Деловой профиль — <b>№{bfb}</b>\n"
        )
    else:
        text += (
            "\n💎 <b>Хочешь полный разбор?</b>\n"
            "• Почему победитель выигрывает\n"
            "• Что слабее у остальных\n"
            "• Какое фото для Telegram, знакомств и делового профиля\n\n"
            "👇 Жми, чтобы узнать"
        )

    return text