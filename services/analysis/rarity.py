"""
Редкие / легендарные архетипы.

Логика:
- Есть фиксированный список ЛЕГЕНДАРНЫХ архетипов (8 штук).
- AI генерит обычный архетип (см. prompts/photo_analysis_v3.py).
- На бэке бросаем кубик: с шансом LEGENDARY_CHANCE (3%)
  подменяем архетип на случайный легендарный.
- Защита от инфляции:
    * не чаще одного раза в LEGENDARY_COOLDOWN_DAYS (7) дней;
    * не раньше LEGENDARY_MIN_ANALYSES (3) анализов у юзера.
- Если легендарка была недавно — шанс понижается
  до LEGENDARY_CHANCE_REDUCED (1%), но не до нуля.

ВАЖНО:
- Все имена архетипов хранятся в UPPERCASE (как в archetypes.py).
- Список легендарных НЕ должен пересекаться с обычными
  ключевыми словами из services/cards/themes.py, иначе
  тема карточки подберётся неправильно. Поэтому имена
  намеренно длинные и специфичные.
- Редкость определяется ПОСТФАКТУМ (не AI), чтобы шанс
  был честным и управляемым.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from sqlalchemy import select

from database.connection import async_session
from database.models import UserEngagement
from utils.logging import get_logger

logger = get_logger(__name__)


# ============================================================
# КОНСТАНТЫ
# ============================================================

# Список легендарных архетипов.
# Все — капсом, длинные, эпичные. Не пересекаются с ключевыми
# словами обычных тем (хаос/калм/лидер/интеллект/...).
LEGENDARY_ARCHETYPES: list[str] = [
    "ХРАНИТЕЛЬ ТИШИНЫ",
    "НЕКРОНОМИКОН В КАРМАНЕ",
    "ПОСЛЕДНИЙ ИЗ ЛЕГЕНД",
    "ТОТ КОГО НЕ ДОЛЖНО БЫЛО БЫТЬ",
    "ИМПЕРАТОР БЕЗ ТРОНА",
    "ГЛАВНЫЙ ГЕРОЙ ЧУЖОГО СНА",
    "ФЕНИКС ИЗ ПЕПЛА",
    "АРХИТЕКТОР РЕАЛЬНОСТИ",
]

# Базовый шанс выпадения легендарки
LEGENDARY_CHANCE: float = 0.03  # 3%

# Пониженный шанс, если легендарка была недавно
LEGENDARY_CHANCE_REDUCED: float = 0.01  # 1%

# Кулдаун между легендарками (дней)
LEGENDARY_COOLDOWN_DAYS: int = 7

# Минимальное количество анализов до первой легендарки
LEGENDARY_MIN_ANALYSES: int = 3

# Очки за легендарный архетип (вместо обычных 30 за new_archetype)
LEGENDARY_POINTS: int = 300


# ============================================================
# БАЗОВЫЕ ФУНКЦИИ
# ============================================================

def normalize(name: Optional[str]) -> str:
    """
    Нормализует имя архетипа: strip + upper.
    Совпадает с логикой archetypes.py, чтобы ключи в
    коллекции и в проверке редкости были одинаковые.
    """
    if not name:
        return ""
    return name.strip().upper()


def is_legendary(name: Optional[str]) -> bool:
    """
    Проверяет, является ли архетип легендарным.
    Сравнение по нормализованному имени.
    """
    norm = normalize(name)
    if not norm:
        return False
    return norm in LEGENDARY_ARCHETYPES


def pick_random_legendary(exclude: Optional[str] = None) -> str:
    """
    Возвращает случайный легендарный архетип.
    Если exclude задан — старается не вернуть его
    (полезно, если у юзера уже есть этот архетип
    и хочется разнообразия).
    """
    pool = LEGENDARY_ARCHETYPES
    if exclude:
        exclude_norm = normalize(exclude)
        filtered = [a for a in pool if a != exclude_norm]
        # Если после фильтра список пуст — возвращаем из полного
        pool = filtered or pool
    return random.choice(pool)


# ============================================================
# ПРОВЕРКА УСЛОВИЙ (cooldown / min_analyses)
# ============================================================

def _in_cooldown(last_legendary_at: Optional[datetime]) -> bool:
    """
    True, если с последней легендарки прошло меньше
    LEGENDARY_COOLDOWN_DAYS дней.
    """
    if last_legendary_at is None:
        return False

    now = datetime.now(timezone.utc)
    # На случай naive datetime из БД — приводим к UTC
    if last_legendary_at.tzinfo is None:
        last_legendary_at = last_legendary_at.replace(tzinfo=timezone.utc)

    delta = now - last_legendary_at
    return delta < timedelta(days=LEGENDARY_COOLDOWN_DAYS)


# ============================================================
# ГЛАВНАЯ ФУНКЦИЯ
# ============================================================

async def maybe_make_legendary(
    user_id: int,
    current_archetype: str,
) -> Tuple[str, bool]:
    """
    Решает, станет ли текущий архетип легендарным.

    Возвращает:
        (итоговый_архетип, is_legendary)

    Логика:
    1. Читаем UserEngagement (кол-во анализов, last_legendary_at).
    2. Если анализов < LEGENDARY_MIN_ANALYSES — не легендарка.
    3. Определяем шанс: базовый или пониженный (если в кулдауне).
    4. Бросаем кубик.
    5. Если выпало — возвращаем случайный легендарный архетип
       и True. Иначе — исходный архетип и False.

    ВАЖНО:
    - НЕ записывает last_legendary_at в БД. Это делает
      вызывающий код (analysis.py) после успешного сохранения
      профиля и начисления очков, чтобы не было рассинхрона.
    - Не кидает исключения: при любой ошибке — возвращает
      исходный архетип и False (легендарка не должна ломать
      основной поток анализа).
    """
    if not current_archetype:
        return current_archetype, False

    try:
        async with async_session() as session:
            eng = (await session.execute(
                select(UserEngagement).where(UserEngagement.user_id == user_id)
            )).scalar_one_or_none()

            total_analyses = eng.total_analyses if eng else 0
            last_legendary_at = getattr(eng, "last_legendary_at", None) if eng else None

        # --- Условие 1: минимум анализов ---
        if total_analyses < LEGENDARY_MIN_ANALYSES:
            return current_archetype, False

        # --- Условие 2: шанс (базовый или пониженный) ---
        chance = (
            LEGENDARY_CHANCE_REDUCED
            if _in_cooldown(last_legendary_at)
            else LEGENDARY_CHANCE
        )

        if random.random() >= chance:
            return current_archetype, False

        # --- Условие 3: выбираем легендарный, не совпадающий с текущим ---
        # Если текущий уже легендарный (не должно случаться,
        # но на всякий) — берём другой.
        new_archetype = pick_random_legendary(exclude=current_archetype)
        logger.info(
            f"[RARITY] user={user_id} legendary! "
            f"'{current_archetype}' -> '{new_archetype}'"
        )
        return new_archetype, True

    except Exception:
        logger.exception(f"[RARITY] failed for user={user_id}")
        return current_archetype, False


async def mark_legendary_received(user_id: int) -> None:
    """
    Записывает last_legendary_at = now для юзера.
    Вызывается из analysis.py ПОСЛЕ успешного сохранения
    профиля и начисления очков.

    Отдельная функция — чтобы не мешать транзакциям
    основного потока.
    """
    try:
        async with async_session() as session:
            eng = (await session.execute(
                select(UserEngagement).where(UserEngagement.user_id == user_id)
            )).scalar_one_or_none()

            if eng is None:
                return

            eng.last_legendary_at = datetime.now(timezone.utc)
            await session.commit()
    except Exception:
        logger.exception(f"[RARITY] mark_legendary_received failed user={user_id}")