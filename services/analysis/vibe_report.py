"""
Вайб-отчёт (Шаг 1.3).

Собирает данные юзера → считает перцентили → готовит рекомендации
→ зовёт AI → возвращает готовый отчёт.

Два режима:
- build_vibe_report(user_id, weekly=False) — портрет по запросу.
- build_vibe_report(user_id, weekly=True)  — недельная сводка.

Возврат:
    {
        "available": bool,      # доступен ли отчёт (>= 3 анализов)
        "reason": str,          # если not available — почему
        "text": str,            # основной текст отчёта (HTML)
        "summary": str,         # 1 фраза для картинки
        "recommendation": str,  # одна рекомендация
    }

ВАЖНО:
- НЕ хранит отчёты в БД (по решению — без кэша).
- Любая ошибка AI → возвращает available=True, но с fallback-текстом.
- Все обращения к БД — внутри async with, ничего не тащим наружу.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select

from database.connection import async_session
from database.models import (
    DailyChallenge,
    Message,
    PhotoAnalysis,
    Profile,
    Test,
    User,
    UserChallenge,
    UserEngagement,
    UserTest,
)
from services.engagement.points import title_for_level
from services.analysis.rarity import is_legendary
from services.ai.factory import get_ai_provider
from utils.logging import get_logger

logger = get_logger(__name__)


# ============================================================
# КОНСТАНТЫ
# ============================================================

# Минимум анализов для доступа к отчёту
MIN_ANALYSES_FOR_REPORT = 3

# Сколько последних профилей отдавать AI
PROFILES_LIMIT = 10

# Сколько последних архетипов учитывать для «уникальных»
UNIQUE_ARCHETYPES_WINDOW = 200

# Размер окна для недельной сводки
WEEKLY_WINDOW_DAYS = 7


# ============================================================
# ВСПОМОГАТЕЛЬНОЕ: перцентиль
# ============================================================

async def _percentile(
    session,
    column,
    my_value: int,
    min_value: int = 0,
) -> Optional[int]:
    """
    Возвращает перцентиль юзера по заданной колонке Profile
    (например, Profile.charisma) среди ВСЕХ профилей,
    у которых значение >= min_value.

    Формула: pct = round( (кол-во_меньших / всего) * 100 ) + 1

    Возвращает:
        1..100 — если данных достаточно (>= 20 записей).
        None — если данных мало (не позорим юзера «топ-100%»).
    """
    try:
        total = (await session.execute(
            select(func.count(Profile.id)).where(column >= min_value)
        )).scalar_one()

        if total < 20:
            return None

        less = (await session.execute(
            select(func.count(Profile.id)).where(
                column >= min_value, column < my_value
            )
        )).scalar_one()

        pct = int(round(less / total * 100)) + 1
        return max(1, min(100, pct))
    except Exception:
        logger.exception("[VIBE] percentile failed")
        return None


async def _percentile_points(session, my_value: int) -> Optional[int]:
    """То же, но по total_points из UserEngagement."""
    try:
        total = (await session.execute(
            select(func.count(UserEngagement.id)).where(UserEngagement.total_points > 0)
        )).scalar_one()

        if total < 20:
            return None

        less = (await session.execute(
            select(func.count(UserEngagement.id)).where(
                UserEngagement.total_points > 0,
                UserEngagement.total_points < my_value,
            )
        )).scalar_one()

        pct = int(round(less / total * 100)) + 1
        return max(1, min(100, pct))
    except Exception:
        logger.exception("[VIBE] percentile points failed")
        return None


# ============================================================
# ВСПОМОГАТЕЛЬНОЕ: собрать профили
# ============================================================

async def _load_profiles(session, user_id: int) -> List[Dict[str, Any]]:
    """
    Возвращает список последних профилей юзера (до PROFILES_LIMIT).
    Каждый — словарь {archetype, vibe, scores, created_at}.
    """
    rows = (await session.execute(
        select(Profile)
        .where(Profile.user_id == user_id)
        .order_by(Profile.id.desc())
        .limit(PROFILES_LIMIT)
    )).scalars().all()

    result = []
    for p in rows:
        result.append({
            "archetype": p.archetype or "",
            "vibe": (p.vibe or "")[:120],
            "scores": {
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
            },
            "created_at": p.created_at.isoformat() if p.created_at else None,
        })
    return result


# ============================================================
# ВСПОМОГАТЕЛЬНОЕ: уникальные архетипы
# ============================================================

async def _count_unique_archetypes(session, user_id: int) -> int:
    rows = (await session.execute(
        select(Profile.archetype)
        .where(Profile.user_id == user_id)
        .order_by(Profile.id.desc())
        .limit(UNIQUE_ARCHETYPES_WINDOW)
    )).scalars().all()

    seen = set()
    for arch in rows:
        if arch:
            seen.add(arch.strip().upper())
    return len(seen)


async def _count_legendaries(session, user_id: int) -> int:
    rows = (await session.execute(
        select(Profile.archetype)
        .where(Profile.user_id == user_id)
        .order_by(Profile.id.desc())
        .limit(UNIQUE_ARCHETYPES_WINDOW)
    )).scalars().all()

    seen = set()
    for arch in rows:
        if arch and is_legendary(arch):
            seen.add(arch.strip().upper())
    return len(seen)


# ============================================================
# ВСПОМОГАТЕЛЬНОЕ: недельная статистика
# ============================================================

async def _load_weekly(session, user_id: int) -> Dict[str, int]:
    """
    Считает метрики за последние WEEKLY_WINDOW_DAYS дней:
    анализы, сообщения, шеринги, тесты, очки, активные дни, стрик.

    ВАЖНО:
    - «Активные дни» — считаем по events (заходы) за окно.
    - Стрик в начале/конце берём по UserEngagement (текущий).
      «Стрик в начале» = current_streak - active_days (не меньше 0).
    """
    since = datetime.now(timezone.utc) - timedelta(days=WEEKLY_WINDOW_DAYS)

    # Анализы
    analyses = (await session.execute(
        select(func.count(PhotoAnalysis.id))
        .where(PhotoAnalysis.user_id == user_id)
        .where(PhotoAnalysis.created_at >= since)
    )).scalar_one()

    # Сообщения (отправленные)
    messages = (await session.execute(
        select(func.count(Message.id))
        .where(Message.sender_id == user_id)
        .where(Message.created_at >= since)
    )).scalar_one()

    # Тесты
    tests = (await session.execute(
        select(func.count(UserTest.id))
        .where(UserTest.user_id == user_id)
        .where(UserTest.created_at >= since)
    )).scalar_one()

    # События — считаем уникальные дни захода
    # Используем func.date() — Postgres вернёт Date
    try:
        from database.models import Event
        days_rows = (await session.execute(
            select(func.date(Event.created_at))
            .where(Event.user_id == user_id)
            .where(Event.created_at >= since)
            .where(Event.name.in_(["new_users", "photo_sent", "analysis_started"]))
            .distinct()
        )).scalars().all()
        active_days = len(days_rows)
    except Exception:
        logger.exception("[VIBE] active_days failed")
        active_days = 0

    # Шеринги (из Event)
    try:
        from database.models import Event
        shares = (await session.execute(
            select(func.count(Event.id))
            .where(Event.user_id == user_id)
            .where(Event.created_at >= since)
            .where(Event.name == "share_generated")
        )).scalar_one()
    except Exception:
        shares = 0

    # Очки: разницу total_points не знаем — берём текущие,
    # для «за неделю» используем приближение (points_gained = 0, AI поймёт).
    # Точные очки за неделю — отдельная задача. Пока — None → 0.
    points_gained = 0

    # Стрик: текущий = eng.current_streak
    eng = (await session.execute(
        select(UserEngagement).where(UserEngagement.user_id == user_id)
    )).scalar_one_or_none()

    streak_end = eng.current_streak if eng else 0
    streak_start = max(0, streak_end - active_days)

    return {
        "active_days": int(active_days),
        "analyses": int(analyses),
        "messages": int(messages),
        "shares": int(shares),
        "tests": int(tests),
        "points_gained": int(points_gained),
        "streak_start": int(streak_start),
        "streak_end": int(streak_end),
    }


# ============================================================
# ВСПОМОГАТЕЛЬНОЕ: рекомендации
# ============================================================

async def _load_recommendations(
    session,
    user_id: int,
    profiles: List[Dict[str, Any]],
    stats: Dict[str, Any],
) -> List[Dict[str, str]]:
    """
    Собирает 1-3 рекомендации для юзера.
    Приоритеты:
    1. Тест, который он ещё не проходил (по убыванию sort_order).
    2. Если легендарных 0 — подсказка «лови легендарку».
    3. Если друзей 0 — «пригласи друга».
    """
    recs: List[Dict[str, str]] = []

    # 1. Непройденный тест
    try:
        passed_subq = (
            select(UserTest.test_id)
            .where(UserTest.user_id == user_id)
        )
        test = (await session.execute(
            select(Test)
            .where(Test.is_active.is_(True))
            .where(Test.is_premium.is_(False))
            .where(Test.id.notin_(passed_subq))
            .order_by(Test.sort_order.asc())
            .limit(1)
        )).scalar_one_or_none()

        if test is not None:
            recs.append({
                "type": "test",
                "code": f"test_{test.id}",
                "title": test.name,
            })
    except Exception:
        logger.exception("[VIBE] test recommendation failed")

    # 2. Легендарка
    if stats.get("legendary_count", 0) == 0 and stats.get("total_analyses", 0) >= 3:
        recs.append({
            "type": "legendary",
            "code": "hunt_legendary",
            "title": "Лови легендарный архетип (шанс 3%)",
        })

    # 3. Друзья
    if stats.get("total_referrals", 0) == 0:
        recs.append({
            "type": "referral",
            "code": "invite_friend",
            "title": "Пригласи друга — сравните вайбы",
        })

    return recs[:3]


# ============================================================
# ГЛАВНАЯ ФУНКЦИЯ
# ============================================================

async def build_vibe_report(
    user_id: int,
    weekly: bool = False,
) -> Dict[str, Any]:
    """
    Строит вайб-отчёт для юзера.

    weekly=False — портрет по запросу.
    weekly=True  — недельная сводка.

    Возвращает dict (см. докстринг модуля).
    """
    # ---- Проверка доступа ----
    async with async_session() as session:
        user = (await session.execute(
            select(User).where(User.id == user_id)
        )).scalar_one_or_none()

        if user is None:
            return {
                "available": False,
                "reason": "user_not_found",
                "text": "",
                "summary": "",
                "recommendation": "",
            }

        total_analyses = (await session.execute(
            select(func.count(PhotoAnalysis.id))
            .where(PhotoAnalysis.user_id == user_id)
        )).scalar_one()

        if not weekly and total_analyses < MIN_ANALYSES_FOR_REPORT:
            return {
                "available": False,
                "reason": "not_enough_analyses",
                "have": int(total_analyses),
                "need": MIN_ANALYSES_FOR_REPORT,
                "text": "",
                "summary": "",
                "recommendation": "",
            }

        # ---- Сбор данных ----
        profiles = await _load_profiles(session, user_id)
        unique_archetypes = await _count_unique_archetypes(session, user_id)
        legendary_count = await _count_legendaries(session, user_id)

        eng = (await session.execute(
            select(UserEngagement).where(UserEngagement.user_id == user_id)
        )).scalar_one_or_none()

        stats = {
            "total_analyses": int(total_analyses),
            "total_points": eng.total_points if eng else 0,
            "level": eng.level if eng else 1,
            "title": title_for_level(eng.level if eng else 1),
            "current_streak": eng.current_streak if eng else 0,
            "max_streak": eng.max_streak if eng else 0,
            "total_messages": eng.total_messages if eng else 0,
            "total_tests": eng.total_tests if eng else 0,
            "total_shares": eng.total_shares if eng else 0,
            "total_referrals": eng.total_referrals if eng else 0,
            "unique_archetypes": unique_archetypes,
            "legendary_count": legendary_count,
        }

        # ---- Перцентили ----
        # Берём последний (свежий) профиль для характеристик
        latest = profiles[0] if profiles else {}
        latest_scores = latest.get("scores", {}) if latest else {}

        tops: Dict[str, Optional[int]] = {
            "charisma_pct": await _percentile(
                session, Profile.charisma, int(latest_scores.get("charisma", 0))
            ),
            "chaos_pct": await _percentile(
                session, Profile.chaos, int(latest_scores.get("chaos", 0))
            ),
            "humor_pct": await _percentile(
                session, Profile.humor, int(latest_scores.get("humor", 0))
            ),
            "points_pct": await _percentile_points(
                session, stats["total_points"]
            ),
        }

        # ---- Недельные метрики ----
        weekly_data: Dict[str, int] = {}
        if weekly:
            weekly_data = await _load_weekly(session, user_id)

        # ---- Рекомендации ----
        recommendations = await _load_recommendations(
            session, user_id, profiles, stats
        )

        # ---- Снимок для AI (detached!) ----
        user_snapshot = {
            "first_name": user.first_name or "Игрок",
            "username": user.username or "",
        }

    # ---- Всё, что нужно AI — уже вне сессии ----
    profile_data = {
        "user": user_snapshot,
        "profiles": profiles,
        "stats": stats,
        "weekly": weekly_data,
        "tops": tops,
        "recommendations": recommendations,
    }

    # ---- Вызов AI ----
    try:
        provider = await get_ai_provider()
        result = await provider.generate_vibe_report(profile_data, weekly=weekly)
        text = (result.get("text") or "").strip()
        summary = (result.get("summary") or "").strip()
        recommendation = (result.get("recommendation") or "").strip()

        if not text:
            text = _fallback_text(user_snapshot, stats, weekly)
        if not summary:
            summary = _fallback_summary(stats)
        if not recommendation and recommendations:
            recommendation = recommendations[0].get("title", "")

        return {
            "available": True,
            "reason": "ok",
            "text": text,
            "summary": summary,
            "recommendation": recommendation,
        }

    except Exception:
        logger.exception("[VIBE] AI report failed")
        return {
            "available": True,
            "reason": "ai_failed",
            "text": _fallback_text(user_snapshot, stats, weekly),
            "summary": _fallback_summary(stats),
            "recommendation": (
                recommendations[0]["title"] if recommendations else ""
            ),
        }


# ============================================================
# FALLBACK (если AI упал)
# ============================================================

def _fallback_summary(stats: Dict[str, Any]) -> str:
    if stats.get("legendary_count", 0) > 0:
        return f"Легендарных архетипов: {stats['legendary_count']}"
    if stats.get("unique_archetypes", 0) > 0:
        return f"Уникальных архетипов: {stats['unique_archetypes']}"
    return "Твой вайб растёт"


def _fallback_text(
    user: Dict[str, str],
    stats: Dict[str, Any],
    weekly: bool,
) -> str:
    name = user.get("first_name", "Игрок")
    if weekly:
        return (
            f"<b>{name}</b>, недельная сводка временно недоступна.\n\n"
            f"Твой стрик: <b>{stats.get('current_streak', 0)}</b> дней. "
            f"Возвращайся — AI уже готовит новый отчёт."
        )
    return (
        f"<b>{name}</b>, AI-отчёт временно недоступен.\n\n"
        f"Ты собрал <b>{stats.get('unique_archetypes', 0)}</b> архетипов "
        f"и <b>{stats.get('total_points', 0)}</b> очков. "
        f"Попробуй позже — AI уже чинится."
    )