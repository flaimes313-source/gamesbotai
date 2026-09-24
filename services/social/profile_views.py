"""
Кто посмотрел профиль (Этап 3).

Два режима:
1. Реальные просмотры — логируются при матчинге/сравнении/топах.
   Юзеру показываем «N человек зашли в твой профиль» (без имён).
2. Псевдо-просмотры — для юзеров, которых не было 4+ дня.
   Показываем «Твой вайб заинтересовал 🔥-игрока».

Правила:
- Не пишем имена (приватность).
- Не пишем «кто именно» — только «сколько» и «какие типы».
- Шлём через hub (kind="profile_views", priority=4).
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select

from database.connection import async_session
from database.models import Profile, ProfileView, User
from utils.logging import get_logger

logger = get_logger(__name__)


# ============================================================
# КОНСТАНТЫ
# ============================================================
MIN_DAYS_AWAY_FOR_PSEUDO = 4      # если не был 4+ дней → псевдо
REAL_VIEWS_WINDOW_DAYS = 7        # окно реальных просмотров


# ============================================================
# ЛОГ ПРОСМОТРА
# ============================================================
async def log_view(viewer_id: int, viewed_id: int, source: str = "matching") -> None:
    """
    Записывает факт просмотра профиля.
    Не падает при ошибках — просто логирует.
    """
    if viewer_id == viewed_id:
        return  # себя не считаем

    try:
        async with async_session() as session:
            session.add(ProfileView(
                viewer_id=viewer_id,
                viewed_id=viewed_id,
                source=source,
            ))
            await session.commit()
    except Exception:
        logger.exception(f"[VIEWS] log failed viewer={viewer_id} viewed={viewed_id}")


# ============================================================
# РЕАЛЬНЫЕ ПРОСМОТРЫ
# ============================================================
async def get_recent_viewers_count(user_id: int) -> int:
    """
    Сколько РАЗНЫХ людей смотрели профиль за окно.
    """
    since = datetime.now(timezone.utc) - timedelta(days=REAL_VIEWS_WINDOW_DAYS)

    try:
        async with async_session() as session:
            cnt = (await session.execute(
                select(func.count(func.distinct(ProfileView.viewer_id)))
                .where(ProfileView.viewed_id == user_id)
                .where(ProfileView.created_at >= since)
            )).scalar_one()
            return int(cnt)
    except Exception:
        logger.exception("[VIEWS] count failed")
        return 0


async def get_viewers_archetypes(user_id: int, limit: int = 3) -> List[str]:
    """
    Возвращает список архетипов тех, кто смотрел профиль.
    Анонимно — без имён.
    """
    since = datetime.now(timezone.utc) - timedelta(days=REAL_VIEWS_WINDOW_DAYS)

    try:
        async with async_session() as session:
            # Подзапрос: viewer_id-ы, кто смотрел
            subq = (
                select(ProfileView.viewer_id)
                .where(ProfileView.viewed_id == user_id)
                .where(ProfileView.created_at >= since)
                .distinct()
            )

            # Архетипы этих viewer-ов (последние профили)
            rows = (await session.execute(
                select(Profile.archetype)
                .where(Profile.user_id.in_(subq))
                .order_by(Profile.id.desc())
                .limit(limit * 5)
            )).scalars().all()

            # Дедуп
            seen = set()
            result = []
            for a in rows:
                if a and a not in seen:
                    seen.add(a)
                    result.append(a)
                if len(result) >= limit:
                    break

            return result
    except Exception:
        logger.exception("[VIEWS] archetypes failed")
        return []


# ============================================================
# ПСЕВДО-ПРОСМОТРЫ (для отсутствующих)
# ============================================================
def get_pseudo_views(last_active_at: Optional[datetime]) -> Optional[Dict[str, Any]]:
    """
    Для юзеров, которых не было 4+ дней — генерим
    псевдо-«просмотры».

    Возвращает:
        None — если не подходит.
        dict — {"count": int, "types": [str, ...]}.

    Логика:
    - 4-6 дней отсутствия → 1-2 «игрока».
    - 7-13 дней → 2-3 «игрока».
    - 14+ дней → 3-5 «игроков».
    """
    if last_active_at is None:
        return None

    if last_active_at.tzinfo is None:
        last_active_at = last_active_at.replace(tzinfo=timezone.utc)

    now = datetime.now(timezone.utc)
    days = (now - last_active_at).days

    if days < MIN_DAYS_AWAY_FOR_PSEUDO:
        return None

    if days < 7:
        count = random.randint(1, 2)
    elif days < 14:
        count = random.randint(2, 3)
    else:
        count = random.randint(3, 5)

    # Типы игроков — по эмодзи-архетипам
    all_types = ["🔥", "❄️", "⚡", "🌙", "✨", "🎯", "🎭", "🧠", "💥", "🎨"]
    types = random.sample(all_types, min(count, len(all_types)))

    return {"count": count, "types": types}


# ============================================================
# ФОРМИРОВАНИЕ СООБЩЕНИЯ
# ============================================================
def format_profile_views_message(
    real_count: int,
    archetypes: List[str],
    pseudo: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Собирает текст уведомления.

    Приоритет:
    1. Если есть реальные просмотры — используем их.
    2. Иначе — псевдо.
    """
    if real_count > 0:
        lines = [
            "👀 <b>ТВОЙ ПРОФИЛЬ ПОСМОТРЕЛИ</b>",
            "",
            f"Сегодня <b>{real_count}</b> " +
            ("человек зашёл" if real_count > 1 else "человек зашёл") +
            " в твой профиль.",
        ]

        if archetypes:
            lines.append("")
            lines.append("Самый активный интерес — к твоим архетипам:")
            for a in archetypes[:3]:
                lines.append(f"• «{a}»")

        lines.append("")
        lines.append("<i>Имена мы не показываем — приватность важнее 😉</i>")
        return "\n".join(lines)

    if pseudo:
        count = pseudo.get("count", 1)
        types = pseudo.get("types", [])
        types_str = " ".join(types)

        return (
            f"👀 <b>ТВОЙ ПРОФИЛЬ ЖДУТ</b>\n\n"
            f"Твой вайб заинтересовал <b>{count}</b> игроков {types_str}\n\n"
            f"Возвращайся — может, кто-то хочет с тобой познакомиться 👇"
        )

    return ""