"""
«Что обо мне думают?» (Этап C).

Логика:
1. Проверка лимита: Free — 1 раз/день, Pro — безлимит.
2. Сбор данных профиля.
3. AI → результат.
4. Free: 3 характеристики + интрига (hidden_trait).
5. Pro: + расширенный разбор (first_notice, how_seen, improve).
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
    return f"first_impression_{today}"


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
                payload={"type": "first_impression"},
            ))
            await session.commit()
    except Exception:
        pass


async def _collect_data(user_id: int) -> Optional[Dict[str, Any]]:
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
        if profile is None:
            return None

        return {
            "user_name": user.first_name or "Игрок",
            "archetype": profile.archetype or "",
            "vibe": profile.vibe or "",
            "charisma": profile.charisma,
            "confidence": profile.confidence,
            "humor": profile.humor,
            "energy": profile.energy,
            "sociability": profile.sociability,
            "creativity": profile.creativity,
        }


async def generate_first_impression_for_user(
    user_id: int,
    telegram_id: int,
) -> Optional[Dict[str, Any]]:
    allowed, is_pro = await _check_limit(user_id, telegram_id)
    if not allowed:
        return {
            "allowed": False,
            "reason": "limit_reached",
            "is_pro": False,
        }

    data = await _collect_data(user_id)
    if data is None:
        return {
            "allowed": False,
            "reason": "no_profile",
            "is_pro": is_pro,
        }

    try:
        provider = await get_ai_provider()
        result = await provider.generate_first_impression(profile_data=data)
    except Exception:
        logger.exception("[FIRST_IMPRESSION] AI failed")
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
        "main_text": result.get("main_text", ""),
        "confidence": int(result.get("confidence", 0)),
        "interest": int(result.get("interest", 0)),
        "openness": int(result.get("openness", 0)),
        "hidden_trait": result.get("hidden_trait", ""),
        # Поля для Pro
        "first_notice": result.get("first_notice", ""),
        "how_seen": result.get("how_seen", ""),
        "improve": result.get("improve", ""),
    }


def format_first_impression(result: Dict[str, Any]) -> str:
    if not result.get("allowed"):
        reason = result.get("reason")
        if reason == "limit_reached":
            return (
                "👀 <b>Что обо мне думают?</b>\n\n"
                "Ты уже использовал бесплатный анализ на сегодня.\n\n"
                "💎 <b>С Pro — безлимит.</b>"
            )
        if reason == "no_profile":
            return (
                "👀 <b>Что обо мне думают?</b>\n\n"
                "Сначала отправь фото — я должен знать твой вайб."
            )
        if reason == "ai_failed":
            return (
                "😔 <b>AI сейчас перегружен</b>\n\n"
                "GigaChat временно не отвечает — попробуй через минуту.\n\n"
                "🔁 <b>Лимит Free не потрачен.</b>"
            )
        return "😔 Не получилось. Попробуй позже."

    # ====================================================
    # БАЗОВАЯ ЧАСТЬ (Free + Pro)
    # ====================================================
    text = (
        f"👀 <b>ПЕРВОЕ ВПЕЧАТЛЕНИЕ О ТЕБЕ</b>\n\n"
        f"{result.get('main_text', '')}\n\n"
        f"Уверенность — <b>{result.get('confidence', 0)}%</b>\n"
        f"Интересность — <b>{result.get('interest', 0)}%</b>\n"
        f"Открытость — <b>{result.get('openness', 0)}%</b>\n\n"
    )

    if result.get("is_pro"):
        # ====================================================
        # PRO: полный разбор
        # ====================================================
        text += "✨ <b>Полный разбор (PRO)</b>\n\n"

        hidden = result.get("hidden_trait", "")
        if hidden:
            text += f"🔒 <b>Черта, которую замечают сразу:</b>\n<i>{hidden}</i>\n\n"

        first_notice = result.get("first_notice", "")
        if first_notice:
            text += f"👁 <b>Что замечают первым:</b>\n{first_notice}\n\n"

        how_seen = result.get("how_seen", "")
        if how_seen:
            text += f"👥 <b>Как тебя видят незнакомцы:</b>\n{how_seen}\n\n"

        improve = result.get("improve", "")
        if improve:
            text += f"💡 <b>Что можно усилить:</b>\n{improve}\n"
    else:
        # ====================================================
        # FREE: интрига + блок Pro
        # ====================================================
        text += (
            "😈 <b>А теперь самое интересное...</b>\n\n"
            "Какой ты кажешься человеку, который увидит тебя впервые?\n\n"
            f"🔒 <i>{result.get('hidden_trait', 'Есть одна черта, которую люди замечают сразу.')}</i>\n\n"
            "💎 <b>Открыть полный разбор:</b>\n"
            "• Что именно замечают первым\n"
            "• Как тебя воспринимают незнакомцы\n"
            "• Что можно усилить\n\n"
            "👇 Жми, чтобы узнать"
        )

    return text