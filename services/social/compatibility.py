"""
Совместимость со звёздами (Этап 3).

Юзер жмёт кнопку → AI сравнивает его вайб с 20 персонажами
→ топ-3 с процентами.

Список персонажей встроен в этот модуль (не в data/),
чтобы не зависеть от .gitignore и структуры папок на BotHost.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import select

from database.connection import async_session
from database.models import Profile, User
from services.ai.factory import get_ai_provider
from utils.logging import get_logger

logger = get_logger(__name__)


# ============================================================
# СПИСОК ПЕРСОНАЖЕЙ (20 штук)
# ============================================================
# Формат: code, name, emoji, archetype, характеристики (0-100)
CELEBRITIES: List[Dict[str, Any]] = [
    {
        "code": "sherlock",
        "name": "Шерлок Холмс",
        "emoji": "🕵️",
        "archetype": "ХОЛОДНЫЙ УМ В ГОРЯЧЕМ МИРЕ",
        "chaos": 60, "charisma": 55, "humor": 40,
        "energy": 70, "intellect": 98, "creativity": 75,
    },
    {
        "code": "tony_stark",
        "name": "Тони Старк",
        "emoji": "🤖",
        "archetype": "ГЕНИЙ С ЭГО",
        "chaos": 75, "charisma": 95, "humor": 88,
        "energy": 90, "intellect": 95, "creativity": 92,
    },
    {
        "code": "joker",
        "name": "Джокер",
        "emoji": "🃏",
        "archetype": "ХАОС БЕЗ ГРАНИЦ",
        "chaos": 100, "charisma": 70, "humor": 85,
        "energy": 80, "intellect": 75, "creativity": 90,
    },
    {
        "code": "forrest_gump",
        "name": "Форрест Гамп",
        "emoji": "🏃",
        "archetype": "ДОБРЫЙ СЕРДЦЕМ, ПРОСТОЙ ДУШОЙ",
        "chaos": 40, "charisma": 75, "humor": 70,
        "energy": 85, "intellect": 55, "creativity": 45,
    },
    {
        "code": "poirot",
        "name": "Эркюль Пуаро",
        "emoji": "🎩",
        "archetype": "ПЕДАНТ С БЛЕСКОМ",
        "chaos": 30, "charisma": 70, "humor": 55,
        "energy": 50, "intellect": 95, "creativity": 60,
    },
    {
        "code": "jobs",
        "name": "Стив Джобс",
        "emoji": "🍎",
        "archetype": "ПЕРФЕКЦИОНИСТ-МАКСИМАЛИСТ",
        "chaos": 70, "charisma": 88, "humor": 55,
        "energy": 90, "intellect": 92, "creativity": 98,
    },
    {
        "code": "musk",
        "name": "Илон Маск",
        "emoji": "🚀",
        "archetype": "ХАОТИЧНЫЙ ВИЗИОНЕР",
        "chaos": 85, "charisma": 80, "humor": 82,
        "energy": 95, "intellect": 93, "creativity": 96,
    },
    {
        "code": "monroe",
        "name": "Мэрилин Монро",
        "emoji": "💃",
        "archetype": "ОБАЯНИЕ И ТРАГЕДИЯ",
        "chaos": 65, "charisma": 98, "humor": 75,
        "energy": 85, "intellect": 70, "creativity": 80,
    },
    {
        "code": "levi",
        "name": "Леви Аккерман",
        "emoji": "⚔️",
        "archetype": "МОЛЧАЛИВЫЙ ХИЩНИК",
        "chaos": 25, "charisma": 65, "humor": 35,
        "energy": 88, "intellect": 85, "creativity": 55,
    },
    {
        "code": "gojo",
        "name": "Сатору Годжо",
        "emoji": "👓",
        "archetype": "СИЛА В РАССЛАБОНЕ",
        "chaos": 70, "charisma": 95, "humor": 92,
        "energy": 85, "intellect": 90, "creativity": 80,
    },
    {
        "code": "gandalf",
        "name": "Гэндальф",
        "emoji": "🧙",
        "archetype": "СТАРЫЙ МУДРЕЦ С ИСКРОЙ",
        "chaos": 45, "charisma": 82, "humor": 60,
        "energy": 60, "intellect": 95, "creativity": 80,
    },
    {
        "code": "jack_sparrow",
        "name": "Джек Воробей",
        "emoji": "🏴‍☠️",
        "archetype": "ОБАЯТЕЛЬНЫЙ ХАОС",
        "chaos": 95, "charisma": 92, "humor": 95,
        "energy": 80, "intellect": 75, "creativity": 88,
    },
    {
        "code": "da_vinci",
        "name": "Леонардо да Винчи",
        "emoji": "🎨",
        "archetype": "ГЕНИЙ ВСЕХ ВРЕМЁН",
        "chaos": 55, "charisma": 75, "humor": 65,
        "energy": 80, "intellect": 99, "creativity": 99,
    },
    {
        "code": "rocky",
        "name": "Рокки Бальбоа",
        "emoji": "🥊",
        "archetype": "УПОРСТВО И СЕРДЦЕ",
        "chaos": 35, "charisma": 75, "humor": 55,
        "energy": 95, "intellect": 50, "creativity": 45,
    },
    {
        "code": "wednesday",
        "name": "Уэнсдэй Аддамс",
        "emoji": "🖤",
        "archetype": "МРАЧНЫЙ ИНТЕЛЛЕКТ",
        "chaos": 65, "charisma": 70, "humor": 78,
        "energy": 55, "intellect": 92, "creativity": 85,
    },
    {
        "code": "hermione",
        "name": "Гермиона Грейнджер",
        "emoji": "📚",
        "archetype": "УМНИЦА-ПЕРФЕКЦИОНИСТКА",
        "chaos": 40, "charisma": 70, "humor": 55,
        "energy": 80, "intellect": 98, "creativity": 75,
    },
    {
        "code": "rocket",
        "name": "Ракета (GOTG)",
        "emoji": "🦝",
        "archetype": "САРКАЗМ И ГЕНИЙ",
        "chaos": 80, "charisma": 65, "humor": 95,
        "energy": 85, "intellect": 92, "creativity": 88,
    },
    {
        "code": "deadpool",
        "name": "Дэдпул",
        "emoji": "🗡",
        "archetype": "ХАОС-ШУТНИК",
        "chaos": 98, "charisma": 88, "humor": 99,
        "energy": 90, "intellect": 70, "creativity": 85,
    },
    {
        "code": "godfather",
        "name": "Дон Корлеоне",
        "emoji": "🐴",
        "archetype": "СПОКОЙНАЯ СИЛА",
        "chaos": 25, "charisma": 90, "humor": 35,
        "energy": 55, "intellect": 92, "creativity": 65,
    },
    {
        "code": "kuzco",
        "name": "Куско",
        "emoji": "🦙",
        "archetype": "КАПРИЗНЫЙ ИМПЕРАТОР",
        "chaos": 75, "charisma": 88, "humor": 90,
        "energy": 80, "intellect": 65, "creativity": 80,
    },
]


def _find_celebrity(code: str) -> Optional[Dict[str, Any]]:
    for c in CELEBRITIES:
        if c["code"] == code:
            return c
    return None


def _format_celebrities_text() -> str:
    """Собирает строку для промта."""
    lines = []
    for c in CELEBRITIES:
        lines.append(
            f"{c['code']} | {c['name']} | {c['archetype']} | "
            f"chaos={c['chaos']}, charisma={c['charisma']}, "
            f"humor={c['humor']}, energy={c['energy']}, "
            f"intellect={c['intellect']}, creativity={c['creativity']}"
        )
    return "\n".join(lines)


# ============================================================
# СБОР ДАННЫХ ЮЗЕРА
# ============================================================
async def _collect_profile_data(user_id: int) -> Optional[Dict[str, Any]]:
    """Собирает текущий профиль юзера."""
    try:
        async with async_session() as session:
            profile = (await session.execute(
                select(Profile)
                .where(Profile.user_id == user_id)
                .order_by(Profile.id.desc())
                .limit(1)
            )).scalar_one_or_none()

            if profile is None:
                return None

            return {
                "archetype": profile.archetype or "",
                "vibe": profile.vibe or "",
                "chaos": profile.chaos,
                "charisma": profile.charisma,
                "humor": profile.humor,
                "energy": profile.energy,
                "intellect": profile.intellect,
                "creativity": profile.creativity,
                "confidence": profile.confidence,
            }
    except Exception:
        logger.exception("[COMPAT] collect failed")
        return None


# ============================================================
# ГЛАВНАЯ ФУНКЦИЯ
# ============================================================
async def get_compatibility(user_id: int) -> Optional[List[Dict[str, Any]]]:
    """
    Возвращает список топ-3 совпадений:
        [
            {
                "code": "sherlock",
                "name": "Шерлок Холмс",
                "emoji": "🕵️",
                "archetype": "ХОЛОДНЫЙ УМ В ГОРЯЧЕМ МИРЕ",
                "match": 87,
                "reason": "Холодный ум, хаос вокруг, сарказм...",
            },
            ...
        ]

    Возвращает None, если у юзера нет профиля или AI упал.
    """
    # 1. Данные юзера
    profile_data = await _collect_profile_data(user_id)
    if profile_data is None:
        return None

    # 2. Текст со списком персонажей
    celebrities_text = _format_celebrities_text()

    # 3. AI
    try:
        provider = await get_ai_provider()
        result = await provider.generate_compatibility(
            profile_data, celebrities_text
        )
    except Exception:
        logger.exception("[COMPAT] AI failed")
        return None

    raw_results = result.get("results", []) or []
    if not raw_results:
        return None

    # 4. Обогащаем данными персонажей
    enriched = []
    for r in raw_results[:3]:
        code = r.get("code", "")
        celeb = _find_celebrity(code)
        if celeb is None:
            continue
        enriched.append({
            "code": code,
            "name": celeb["name"],
            "emoji": celeb["emoji"],
            "archetype": celeb["archetype"],
            "match": int(r.get("match", 0)),
            "reason": (r.get("reason", "") or "")[:150],
        })

    if not enriched:
        return None

    logger.info(f"[COMPAT] user={user_id} top={[e['code'] for e in enriched]}")
    return enriched


def format_compatibility_message(results: List[Dict[str, Any]]) -> str:
    """Собирает текст сообщения."""
    if not results:
        return "😔 Не удалось определить совместимость. Попробуй позже."

    medals = ["🥇", "🥈", "🥉"]
    lines = ["💥 <b>ТВОЯ СОВМЕСТИМОСТЬ СО ЗВЁЗДАМИ</b>\n"]

    for i, r in enumerate(results):
        medal = medals[i] if i < len(medals) else "•"
        lines.append(
            f"{medal} {r['emoji']} <b>{r['name']}</b> — <b>{r['match']}%</b>\n"
            f"<i>{r['archetype']}</i>\n"
            f"{r['reason']}\n"
        )

    lines.append("━━━━━━━━━━━━━━━━━━")
    lines.append("Сделай ещё анализ — может, твой топ изменится! 🔄")

    return "\n".join(lines)