"""
«Какой ты сегодня?» (Этап B).

Логика:
1. Проверка лимита: Free — 1 раз/день, Pro — безлимит.
2. Сбор данных (последний профиль + последний analysis_json).
3. AI → результат.
4. Кэш: сохраняем в RewardClaim (если Free — 1 раз/день).
5. Возврат: {main_text, scores, danger_line}.

Pro-версия добавляет: locked-поля (что «скрыто» за PRO).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import select

from database.connection import async_session
from database.models import PhotoAnalysis, Profile, RewardClaim, User
from services.ai.factory import get_ai_provider
from services.premium import is_premium
from utils.logging import get_logger

logger = get_logger(__name__)


# ============================================================
# ЛИМИТЫ
# ============================================================
FREE_DAILY_LIMIT = 1


def _today_code() -> str:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return f"today_vibe_{today}"


# ============================================================
# ПРОВЕРКА ЛИМИТА
# ============================================================
async def _check_limit(user_id: int, telegram_id: int) -> tuple[bool, bool]:
    """
    Возвращает (allowed, is_pro).
    - allowed: можно ли генерить сейчас (Free — только 1 раз/день).
    - is_pro: активна ли PRO.
    """
    is_pro = await is_premium(telegram_id)
    if is_pro:
        return True, True

    # Free: 1 раз/день через RewardClaim
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
    """Помечает, что Free-юзер использовал лимит."""
    code = _today_code()
    try:
        async with async_session() as session:
            session.add(RewardClaim(
                user_id=user_id,
                reward_code=code,
                payload={"type": "today_vibe"},
            ))
            await session.commit()
    except Exception:
        # UNIQUE violation (гонка) — ок
        pass


# ============================================================
# СБОР ДАННЫХ
# ============================================================
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

        # Последний analysis_json — для «photo_context»
        analysis = (await session.execute(
            select(PhotoAnalysis)
            .where(PhotoAnalysis.user_id == user_id)
            .order_by(PhotoAnalysis.id.desc())
            .limit(1)
        )).scalar_one_or_none()

        photo_context = "—"
        if analysis and analysis.analysis_json:
            aj = analysis.analysis_json
            photo_context = (
                f"Архетип: {aj.get('archetype', '')}. "
                f"Вайб: {aj.get('vibe', '')}. "
                f"Фишка: {aj.get('funny_trait', '')}."
            )

        return {
            "user_name": user.first_name or "Игрок",
            "archetype": profile.archetype or "",
            "vibe": profile.vibe or "",
            "charisma": profile.charisma,
            "confidence": profile.confidence,
            "energy": profile.energy,
            "sociability": profile.sociability,
            "chaos": profile.chaos,
            "humor": profile.humor,
            "photo_context": photo_context,
        }


# ============================================================
# ГЛАВНАЯ ФУНКЦИЯ
# ============================================================
async def generate_today_vibe_for_user(
    user_id: int,
    telegram_id: int,
) -> Optional[Dict[str, Any]]:
    """
    Возвращает результат или None при ошибке.

    Формат:
        {
            "allowed": bool,
            "reason": "ok" | "limit_reached" | "no_profile" | "ai_failed",
            "is_pro": bool,
            "main_text": str,
            "confidence": int,
            "energy": int,
            "sociability": int,
            "attractiveness": int,
            "danger_line": str,
        }
    """
    # 1. Лимит
    allowed, is_pro = await _check_limit(user_id, telegram_id)
    if not allowed:
        return {
            "allowed": False,
            "reason": "limit_reached",
            "is_pro": False,
        }

    # 2. Данные
    data = await _collect_data(user_id)
    if data is None:
        return {
            "allowed": False,
            "reason": "no_profile",
            "is_pro": is_pro,
        }

    # 3. AI
    try:
        provider = await get_ai_provider()
        result = await provider.generate_today_vibe(
            profile_data={
                "user_name": data["user_name"],
                "archetype": data["archetype"],
                "vibe": data["vibe"],
                "charisma": data["charisma"],
                "confidence": data["confidence"],
                "energy": data["energy"],
                "sociability": data["sociability"],
                "chaos": data["chaos"],
                "humor": data["humor"],
            },
            photo_context=data["photo_context"],
        )
    except Exception:
        logger.exception("[TODAY_VIBE] AI failed")
        return {
            "allowed": False,
            "reason": "ai_failed",
            "is_pro": is_pro,
        }

    # 4. Помечаем использование (для Free)
    if not is_pro:
        await _mark_used(user_id)

    return {
        "allowed": True,
        "reason": "ok",
        "is_pro": is_pro,
        "main_text": result.get("main_text", ""),
        "confidence": int(result.get("confidence", 0)),
        "energy": int(result.get("energy", 0)),
        "sociability": int(result.get("sociability", 0)),
        "attractiveness": int(result.get("attractiveness", 0)),
        "danger_line": result.get("danger_line", ""),
    }


# ============================================================
# ФОРМАТИРОВАНИЕ
# ============================================================
def format_today_vibe(result: Dict[str, Any]) -> str:
    """Собирает текст для отправки."""
    if not result.get("allowed"):
        reason = result.get("reason")
        if reason == "limit_reached":
            return (
                "😎 <b>Какой ты сегодня?</b>\n\n"
                "Ты уже использовал бесплатный анализ на сегодня.\n\n"
                "💎 <b>С Pro — безлимит.</b>"
            )
        if reason == "no_profile":
            return (
                "😎 <b>Какой ты сегодня?</b>\n\n"
                "Сначала отправь фото — я должен знать твой вайб."
            )
        return "😔 Не получилось. Попробуй позже."

    text = (
        f"🔥 <b>СЕГОДНЯ ТЫ ВЫГЛЯДИШЬ КАК:</b>\n\n"
        f"«{result.get('main_text', '')}»\n\n"
        f"Уверенность — <b>{result.get('confidence', 0)}%</b>\n"
        f"Энергия — <b>{result.get('energy', 0)}%</b>\n"
        f"Социальность — <b>{result.get('sociability', 0)}%</b>\n"
        f"Привлекательность — <b>{result.get('attractiveness', 0)}%</b>\n\n"
        f"<i>{result.get('danger_line', '')}</i>"
    )

    if not result.get("is_pro"):
        text += (
            "\n\n🔒 <b>Что доступно с Pro:</b>\n"
            "• Что сегодня снижает твою привлекательность\n"
            "• Как тебя воспринимают окружающие\n"
            "• Сегодняшний уровень харизмы\n"
            "• Что изменить, чтобы выглядеть увереннее\n\n"
            "💎 <b>Открыть полный разбор</b>"
        )

    return text