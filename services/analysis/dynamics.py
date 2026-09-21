"""
Динамика вайба: как менялся профиль между анализами.
"""
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select

from database.connection import async_session
from database.models import PhotoAnalysis
from utils.logging import get_logger

logger = get_logger(__name__)


# 6 главных характеристик (совпадают с тем, что на карточке)
MAIN_FIELDS: List[str] = [
    "chaos",
    "charisma",
    "humor",
    "energy",
    "intellect",
    "creativity",
]

# Человекочитаемые названия
FIELD_LABELS: Dict[str, str] = {
    "chaos": "🔥 ХАОС",
    "charisma": "✨ ХАРИЗМА",
    "humor": "😂 ЮМОР",
    "energy": "💥 ЭНЕРГИЯ",
    "intellect": "🧠 ИНТЕЛЛЕКТ",
    "creativity": "🎨 КРЕАТИВ",
}

# Порог, при котором считаем изменение "плоским"
FLAT_THRESHOLD = 2


def _direction(delta: int) -> str:
    """up / down / flat."""
    if delta > FLAT_THRESHOLD:
        return "up"
    if delta < -FLAT_THRESHOLD:
        return "down"
    return "flat"


def _arrow(direction: str) -> str:
    return {"up": "↑", "down": "↓", "flat": "→"}.get(direction, "")


def format_delta(delta: int) -> str:
    """+33 ↑ / -13 ↓ / +2 →"""
    sign = "+" if delta >= 0 else ""
    return f"{sign}{delta} {_arrow(_direction(delta))}"


async def _fetch_analyses(user_id: int, limit: int) -> List[PhotoAnalysis]:
    """Возвращает последние N анализов (свежие — в конце списка)."""
    async with async_session() as session:
        rows = (await session.execute(
            select(PhotoAnalysis)
            .where(PhotoAnalysis.user_id == user_id)
            .order_by(PhotoAnalysis.created_at.desc())
            .limit(limit)
        )).scalars().all()

    # Разворачиваем: первый — самый старый, последний — самый свежий
    return list(reversed(rows))


def _extract_scores(analysis_json: Optional[dict]) -> Dict[str, int]:
    """Достаёт scores из analysis_json, с fallback на 0."""
    if not analysis_json:
        return {key: 0 for key in MAIN_FIELDS}
    scores = analysis_json.get("scores") or {}
    result: Dict[str, int] = {}
    for key in MAIN_FIELDS:
        try:
            result[key] = int(scores.get(key, 0))
        except (TypeError, ValueError):
            result[key] = 0
    return result


async def get_dynamics(user_id: int, limit: int = 10) -> Dict[str, Any]:
    """
    Собирает динамику вайба по последним N анализам юзера.

    Возвращает:
        {
            "count": int,
            "has_enough_data": bool,
            "period": {"first": datetime, "last": datetime} | None,
            "fields": {
                "chaos": {
                    "label": "🔥 ХАОС",
                    "first": 45,
                    "last": 78,
                    "delta": 33,
                    "direction": "up",
                    "history": [45, 52, 60, 78],
                },
                ...
            },
            "archetypes": ["ПРИЗРАК ХАОСА", ...],
        }
    """
    analyses = await _fetch_analyses(user_id, limit)
    count = len(analyses)

    base: Dict[str, Any] = {
        "count": count,
        "has_enough_data": count >= 2,
        "period": None,
        "fields": {},
        "archetypes": [],
    }

    if count == 0:
        return base

    # Период
    base["period"] = {
        "first": analyses[0].created_at,
        "last": analyses[-1].created_at,
    }

    # История архетипов
    base["archetypes"] = [
        (a.analysis_json or {}).get("archetype", "")
        for a in analyses
    ]

    # Собираем history по каждой характеристике
    for field in MAIN_FIELDS:
        history: List[int] = []
        for a in analyses:
            scores = _extract_scores(a.analysis_json)
            history.append(scores[field])

        first_val = history[0]
        last_val = history[-1]
        delta = last_val - first_val

        base["fields"][field] = {
            "label": FIELD_LABELS.get(field, field),
            "first": first_val,
            "last": last_val,
            "delta": delta,
            "direction": _direction(delta),
            "history": history,
        }

    return base


def get_biggest_changes(dynamics: Dict[str, Any], top: int = 2) -> List[Tuple[str, Dict[str, Any]]]:
    """
    Возвращает top-N характеристик с наибольшим изменением по модулю.
    Возвращает список кортежей (field_key, field_data).
    """
    fields = dynamics.get("fields") or {}
    if not fields:
        return []

    items = sorted(
        fields.items(),
        key=lambda kv: abs(kv[1].get("delta", 0)),
        reverse=True,
    )
    return items[:top]


def get_other_changes(dynamics: Dict[str, Any], exclude: List[str]) -> List[Tuple[str, Dict[str, Any]]]:
    """
    Остальные характеристики, кроме указанных в exclude.
    Возвращает в исходном порядке MAIN_FIELDS.
    """
    fields = dynamics.get("fields") or {}
    result: List[Tuple[str, Dict[str, Any]]] = []
    for key in MAIN_FIELDS:
        if key in exclude:
            continue
        if key in fields:
            result.append((key, fields[key]))
    return result


def build_progress_bar(value: int, width: int = 10) -> str:
    """Прогресс-бар 0..100."""
    value = max(0, min(100, value))
    filled = int(value / 100 * width)
    return "█" * filled + "░" * (width - filled)


def format_period(dt_first, dt_last) -> str:
    """12.09 — 21.09"""
    try:
        return f"{dt_first.strftime('%d.%m')} — {dt_last.strftime('%d.%m')}"
    except Exception:
        return ""