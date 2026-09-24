"""
Гороскоп вайба (Этап 2).

Раз в неделю (вт/пт) в 10:00 по TZ юзера:
- если в БД есть кэш на сегодня → берём оттуда;
- иначе генерим через AI и сохраняем в horoscopes.

Кэш — таблица horoscopes (user_id, date, text), UNIQUE(user_id, date).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import select

from database.connection import async_session
from database.models import (
    Horoscope,
    Profile,
    User,
    UserEngagement,
)
from services.ai.factory import get_ai_provider
from services.engagement.points import title_for_level
from utils.logging import get_logger

logger = get_logger(__name__)


# ============================================================
# УТИЛИТЫ
# ============================================================
def _today_key() -> datetime:
    """
    Возвращает datetime на начало сегодняшнего дня (UTC).
    Используется как ключ для UNIQUE(user_id, date).
    """
    return datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )


# ============================================================
# КЭШ
# ============================================================
async def _load_cached(user_id: int) -> Optional[str]:
    """Ищет гороскоп на сегодня в БД. None — если нет."""
    date_key = _today_key()
    try:
        async with async_session() as session:
            row = (await session.execute(
                select(Horoscope).where(
                    Horoscope.user_id == user_id,
                    Horoscope.date == date_key,
                )
            )).scalar_one_or_none()
            return row.text if row else None
    except Exception:
        logger.exception("[HOROSCOPE] cache load failed")
        return None


async def _save_cache(user_id: int, text: str) -> None:
    """Сохраняет гороскоп в БД. Игнорирует UNIQUE violation."""
    date_key = _today_key()
    try:
        async with async_session() as session:
            session.add(Horoscope(
                user_id=user_id,
                date=date_key,
                text=text,
            ))
            await session.commit()
    except Exception:
        # Скорее всего гонка — уже записали. Игнорим.
        logger.info(f"[HOROSCOPE] cache save skipped (race?) user={user_id}")


# ============================================================
# СБОР ДАННЫХ
# ============================================================
async def _collect_profile_data(user_id: int) -> Optional[Dict[str, Any]]:
    """Собирает данные юзера для промта."""
    try:
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

            eng = (await session.execute(
                select(UserEngagement).where(UserEngagement.user_id == user_id)
            )).scalar_one_or_none()

            return {
                "user_name": user.first_name or "Игрок",
                "archetype": profile.archetype or "",
                "vibe": profile.vibe or "",
                "chaos": profile.chaos,
                "charisma": profile.charisma,
                "humor": profile.humor,
                "energy": profile.energy,
                "intellect": profile.intellect,
                "current_streak": eng.current_streak if eng else 0,
                "level": eng.level if eng else 1,
                "level_title": title_for_level(eng.level if eng else 1),
            }
    except Exception:
        logger.exception("[HOROSCOPE] collect failed")
        return None


# ============================================================
# ГЛАВНАЯ ФУНКЦИЯ
# ============================================================
async def prepare_horoscope(user_id: int) -> Optional[Dict[str, Any]]:
    """
    Готовит payload гороскопа для hub.

    Возвращает:
        None — если нет данных или AI упал.
        dict — {"text": str} для передачи в hub.

    Логика:
    1. Проверяем кэш на сегодня.
    2. Если есть — берём текст оттуда.
    3. Если нет — собираем данные, зовём AI, сохраняем в БД.
    """
    # 1. Кэш
    cached = await _load_cached(user_id)
    if cached:
        logger.info(f"[HOROSCOPE] cache hit user={user_id}")
        return {"text": cached}

    # 2. Сбор данных
    profile_data = await _collect_profile_data(user_id)
    if profile_data is None:
        return None

    # 3. AI
    try:
        provider = await get_ai_provider()
        text = await provider.generate_horoscope(profile_data)
    except Exception:
        logger.exception("[HOROSCOPE] AI failed")
        return None

    if not text:
        return None

    # 4. Обрезаем, если слишком длинный (Telegram лимит 4096)
    if len(text) > 1000:
        text = text[:1000] + "…"

    # 5. Сохраняем в кэш
    await _save_cache(user_id, text)

    return {"text": text}


def format_horoscope_message(text: str) -> str:
    """
    Оборачивает голый текст гороскопа в красивое сообщение.
    """
    return (
        f"🔮 <b>ГОРОСКОП ВАЙБА</b>\n\n"
        f"{text}"
    )