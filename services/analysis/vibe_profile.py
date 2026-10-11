"""
Vibe-профиль (Этап G).

Единый экран со всей сводкой о юзере:
- архетип + легендарка
- уровень / очки / стрик
- характеристики + тренд (с первым анализом)
- коллекция архетипов
- достижения
- рекомендация «что дальше»
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import func, select

from database.connection import async_session
from database.models import (
    Achievement,
    Profile,
    User,
    UserAchievement,
    UserEngagement,
)
from services.analysis.rarity import is_legendary
from services.engagement.archetypes import get_collection_stats
from services.engagement.points import (
    MAX_LEVEL,
    LEVELS,
    points_to_next_level,
    title_for_level,
)
from utils.logging import get_logger

logger = get_logger(__name__)


# ============================================================
# Константы
# ============================================================
PROGRESS_BAR_WIDTH = 10
BAR_FILLED = "█"
BAR_EMPTY = "░"
TREND_UP = "▲"
TREND_DOWN = "▼"
TREND_FLAT = "─"

# Характеристики для показа (порядок важен)
SCORE_FIELDS: List[tuple[str, str]] = [
    ("charisma", "Харизма"),
    ("confidence", "Уверенность"),
    ("humor", "Юмор"),
    ("energy", "Энергия"),
    ("chaos", "Хаос"),
    ("creativity", "Креативность"),
]


# ============================================================
# УТИЛИТЫ
# ============================================================
def progress_bar(value: int, max_value: int = 100, width: int = PROGRESS_BAR_WIDTH) -> str:
    if max_value <= 0:
        return BAR_EMPTY * width
    filled = max(0, min(width, int(value / max_value * width)))
    return BAR_FILLED * filled + BAR_EMPTY * (width - filled)


def format_delta(delta: int) -> str:
    if delta > 0:
        return f"{TREND_UP}+{delta}"
    if delta < 0:
        return f"{TREND_DOWN}{delta}"   # минус уже в числе
    return TREND_FLAT


def _trend_arrow(delta: int) -> str:
    if delta > 0:
        return "📈"
    if delta < 0:
        return "📉"
    return "➖"


# ============================================================
# СБОРКА
# ============================================================
async def build_vibe_profile(user_id: int) -> Optional[Dict[str, Any]]:
    """
    Возвращает полный словарь для рендера Vibe-профиля,
    либо None если у юзера ещё нет профиля.
    """
    async with async_session() as session:
        # --- User ---
        user = (await session.execute(
            select(User).where(User.id == user_id)
        )).scalar_one_or_none()
        if user is None:
            return None

        # --- Профили: первый + последний ---
        first_profile = (await session.execute(
            select(Profile)
            .where(Profile.user_id == user_id)
            .order_by(Profile.id.asc())
            .limit(1)
        )).scalar_one_or_none()

        latest_profile = (await session.execute(
            select(Profile)
            .where(Profile.user_id == user_id)
            .order_by(Profile.id.desc())
            .limit(1)
        )).scalar_one_or_none()

        if latest_profile is None:
            return None

        # --- Engagement ---
        eng = (await session.execute(
            select(UserEngagement).where(UserEngagement.user_id == user_id)
        )).scalar_one_or_none()

        # --- Достижения (кол-во + последние 6) ---
        total_ach = (await session.execute(
            select(func.count(UserAchievement.id))
            .where(UserAchievement.user_id == user_id)
        )).scalar_one()

        total_ach_possible = (await session.execute(
            select(func.count(Achievement.id))
        )).scalar_one()

        recent_ach_rows = (await session.execute(
            select(UserAchievement)
            .where(UserAchievement.user_id == user_id)
            .order_by(UserAchievement.unlocked_at.desc())
            .limit(6)
        )).scalars().all()

        recent_ach_codes = [a.achievement_code for a in recent_ach_rows]

        ach_details_rows = (await session.execute(
            select(Achievement)
            .where(Achievement.code.in_(recent_ach_codes))
        )).scalars().all()

        ach_by_code = {a.code: a for a in ach_details_rows}

        # Собираем «последние 6 достижений» в правильном порядке
        recent_achievements = []
        for code in recent_ach_codes:
            ach = ach_by_code.get(code)
            if ach:
                recent_achievements.append({
                    "code": ach.code,
                    "emoji": ach.emoji,
                    "title": ach.title,
                })

        # --- Снимок полей (до закрытия сессии) ---
        snap = {
            "user_first_name": user.first_name or "Игрок",
            "user_username": user.username,
            "user_created_at": user.created_at,
            "archetype": latest_profile.archetype,
            "description": latest_profile.description or "",
            "vibe": latest_profile.vibe or "",
            "scores": {
                "charisma": latest_profile.charisma,
                "confidence": latest_profile.confidence,
                "humor": latest_profile.humor,
                "energy": latest_profile.energy,
                "chaos": latest_profile.chaos,
                "creativity": latest_profile.creativity,
            },
            "first_scores": {
                "charisma": first_profile.charisma if first_profile else 0,
                "confidence": first_profile.confidence if first_profile else 0,
                "humor": first_profile.humor if first_profile else 0,
                "energy": first_profile.energy if first_profile else 0,
                "chaos": first_profile.chaos if first_profile else 0,
                "creativity": first_profile.creativity if first_profile else 0,
            },
            "total_analyses": eng.total_analyses if eng else 0,
            "total_points": eng.total_points if eng else 0,
            "level": eng.level if eng else 1,
            "current_streak": eng.current_streak if eng else 0,
            "max_streak": eng.max_streak if eng else 0,
            "total_ach": int(total_ach or 0),
            "total_ach_possible": int(total_ach_possible or 0),
            "recent_achievements": recent_achievements,
        }

    # --- Коллекция архетипов (отдельный сервис) ---
    try:
        collection = await get_collection_stats(user_id)
    except Exception:
        logger.exception("[VIBE_PROFILE] collection failed")
        collection = {"unique": 0, "max": 20, "collected": []}

    snap["collection"] = collection
    snap["is_legendary"] = is_legendary(snap["archetype"])

    # --- Уровень и до следующего ---
    lvl = snap["level"]
    pts = snap["total_points"]
    snap["level_title"] = title_for_level(lvl)
    snap["to_next"] = points_to_next_level(pts, lvl) if lvl < MAX_LEVEL else 0

    return snap


# ============================================================
# ФОРМАТИРОВАНИЕ
# ============================================================
def format_vibe_profile(data: Dict[str, Any]) -> str:
    """
    Собирает текст Vibe-профиля. Готовый HTML для Telegram.
    """
    lines: List[str] = []

    # --- Шапка ---
    if data.get("is_legendary"):
        lines.append("👑 <b>VIBE-ПРОФИЛЬ</b>  ✨")
        lines.append("")
        lines.append("🌟 <b>ЛЕГЕНДАРНЫЙ АРХЕТИП:</b>")
        lines.append(f"🧨 <b>{data['archetype']}</b>")
    else:
        lines.append("🎨 <b>VIBE-ПРОФИЛЬ</b>")
        lines.append("")
        lines.append(f"🧨 <b>{data['archetype']}</b>")

    if data.get("vibe"):
        lines.append(f"<i>{data['vibe']}</i>")

    lines.append("")

    # --- Уровень / очки / стрик ---
    lines.append(
        f"🏅 Уровень: <b>{data['level']}/{MAX_LEVEL}</b> — {data['level_title']}"
    )
    lines.append(f"⭐ Очки: <b>{data['total_points']}</b>")

    if data["level"] < MAX_LEVEL and data["to_next"] > 0:
        lines.append(f"📈 До следующего: <b>{data['to_next']}</b> очков")

    if data["current_streak"] > 0:
        lines.append(f"🔥 Стрик: <b>{data['current_streak']}</b> дней")
    if data["max_streak"] > data["current_streak"]:
        lines.append(f"🏆 Рекорд: <b>{data['max_streak']}</b> дней")

    lines.append("")
    lines.append("━" * 15)
    lines.append("")

    # --- Характеристики + тренд ---
    lines.append("📊 <b>ХАРАКТЕРИСТИКИ</b>")
    lines.append("")

    for field_key, label in SCORE_FIELDS:
        cur = data["scores"].get(field_key, 0)
        first = data["first_scores"].get(field_key, 0)
        delta = cur - first

        bar = progress_bar(cur)
        trend = format_delta(delta)

        lines.append(f"<b>{label}</b>  {cur}  <code>{bar}</code>  {trend}")

    if data["total_analyses"] >= 2:
        lines.append("")
        lines.append(
            "<i>Стрелки — изменение с первого анализа.</i>"
        )

    lines.append("")
    lines.append("━" * 15)
    lines.append("")

    # --- Коллекция ---
    col = data["collection"]
    unique = col.get("unique", 0)
    max_col = col.get("max", 20)
    col_bar = progress_bar(unique, max_col)

    lines.append("🎨 <b>КОЛЛЕКЦИЯ АРХЕТИПОВ</b>")
    lines.append(f"<b>{unique}/{max_col}</b>")
    lines.append(f"<code>{col_bar}</code>")
    lines.append("")

    # --- Достижения ---
    lines.append("🏅 <b>ДОСТИЖЕНИЯ</b>")
    lines.append(
        f"<b>{data['total_ach']}/{data['total_ach_possible']}</b>"
    )
    if data["recent_achievements"]:
        lines.append("")
        for a in data["recent_achievements"]:
            lines.append(f"• {a['emoji']} <b>{a['title']}</b>")
    else:
        lines.append("<i>Пока нет — сделай первый анализ!</i>")

    lines.append("")
    lines.append("━" * 15)
    lines.append("")

    # --- Совет ---
    lines.append("💡 <b>ЧТО ДАЛЬШЕ?</b>")
    lines.append(_build_hint(data))

    text = "\n".join(lines)

    # Защита от 4096
    if len(text) > 4000:
        text = text[:3990] + "\n\n<i>…обрезано</i>"

    return text


def _build_hint(data: Dict[str, Any]) -> str:
    """Персональная подсказка — что делать дальше."""
    # 1. Легендарки нет и анализов ≥ 3
    if not data.get("is_legendary") and data["total_analyses"] >= 3:
        return (
            "🌟 У тебя ещё нет <b>легендарного архетипа</b>. "
            "Шанс есть при каждом новом анализе!"
        )

    # 2. Коллекция не собрана
    col = data["collection"]
    if col.get("unique", 0) < col.get("max", 20):
        left = col.get("max", 20) - col.get("unique", 0)
        return (
            f"🎨 До полной коллекции — <b>{left}</b> архетипов. "
            "Отправляй новые фото!"
        )

    # 3. Достижений мало
    if data["total_ach"] < data["total_ach_possible"]:
        return "🏅 Проверь полный список — там есть что открыть."

    # 4. Стрик
    if data["current_streak"] < 7:
        return "🔥 Заходи каждый день — откроешь награду за стрик!"

    # Fallback
    return "Продолжай в том же духе! Твой вайб растёт. 🔥"