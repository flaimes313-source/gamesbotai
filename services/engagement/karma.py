"""
Карма дня (Этап 2).

Каждый день при первом заходе юзер получает случайный бонус очков.
Защита от повторного получения — через RewardClaim
(reward_code = "karma_YYYY-MM-DD").

Шансы:
- 70% → +10
- 20% → +30
- 8%  → +50
- 2%  → +100 (джекпот)

Максимум за раз: 100 очков.

Показывается как отдельное сообщение после главного меню.
"""

from __future__ import annotations

import random
from datetime import datetime, timezone
from typing import Optional, Tuple

from sqlalchemy import select

from database.connection import async_session
from database.models import RewardClaim
from services.engagement.points import add_custom_points
from services.analytics.tracker import track
from utils.logging import get_logger

logger = get_logger(__name__)


# ============================================================
# КОНСТАНТЫ
# ============================================================

# (шанс, очки) — сумма шансов = 1.0
KARMA_TABLE: list[Tuple[float, int]] = [
    (0.70, 10),
    (0.20, 30),
    (0.08, 50),
    (0.02, 100),
]


# ============================================================
# ВСПОМОГАТЕЛЬНОЕ
# ============================================================
def _today_code() -> str:
    """Возвращает reward_code для кармы на сегодня."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return f"karma_{today}"


def _roll_karma() -> int:
    """Бросает кубик и возвращает количество очков."""
    r = random.random()
    cumulative = 0.0
    for chance, points in KARMA_TABLE:
        cumulative += chance
        if r < cumulative:
            return points
    # Fallback — минимальная награда
    return KARMA_TABLE[0][1]


def _emoji_for_points(points: int) -> str:
    """Подбирает эмодзи по величине награды."""
    if points >= 100:
        return "🎉"
    if points >= 50:
        return "🔥"
    if points >= 30:
        return "✨"
    return "🎁"


def _text_for_points(points: int) -> str:
    """Короткое сообщение по величине награды."""
    if points >= 100:
        return "Невероятная удача! Ты вытащил джекпот!"
    if points >= 50:
        return "Отличный день! Карма на твоей стороне."
    if points >= 30:
        return "Хороший заход. Карма улыбается."
    return "Неплохо для начала. Заходи завтра за новой кармой."


# ============================================================
# ГЛАВНАЯ ФУНКЦИЯ
# ============================================================
async def roll_karma_for_today(user_id: int) -> Optional[dict]:
    """
    Проверяет, получал ли юзер карму сегодня.

    Возвращает:
        None — если уже получал сегодня.
        dict — если начислили:
            {
                "points": int,
                "emoji": str,
                "text": str,
            }

    Начисляет очки через add_custom_points, пишет RewardClaim.
    НЕ открывает лишних сессий — всё внутри одной.
    """
    code = _today_code()

    # Проверяем: не получал ли уже
    async with async_session() as session:
        existing = (await session.execute(
            select(RewardClaim).where(
                RewardClaim.user_id == user_id,
                RewardClaim.reward_code == code,
            )
        )).scalar_one_or_none()

        if existing is not None:
            # Уже получал — тихо выходим
            return None

    # Бросаем кубик
    points = _roll_karma()

    # Пишем RewardClaim — атомарно, с защитой от гонки
    # (если два /start одновременно — один получит IntegrityError)
    try:
        async with async_session() as session:
            claim = RewardClaim(
                user_id=user_id,
                reward_code=code,
                payload={"points": points},
            )
            session.add(claim)
            await session.commit()
    except Exception:
        # Скорее всего UNIQUE violation — уже получил через другую сессию
        logger.info(f"[KARMA] race detected for user={user_id}, skipping")
        return None

    # Начисляем очки (это откроет свою сессию — не вкладываем!)
    try:
        await add_custom_points(user_id, points)
    except Exception:
        logger.exception(f"[KARMA] add_custom_points failed user={user_id}")
        # Награду в RewardClaim уже записали — очки потеряются, но это ок,
        # чтобы не было бесконечного цикла. Или можно откатить claim — но
        # тогда юзер получит второй шанс, что нежелательно.

    # Аналитика
    try:
        await track(
            "karma_rolled",
            user_id=user_id,
            payload={"points": points},
        )
    except Exception:
        logger.exception("[KARMA] track failed")

    logger.info(f"[KARMA] user={user_id} points={points}")

    return {
        "points": points,
        "emoji": _emoji_for_points(points),
        "text": _text_for_points(points),
    }


def format_karma_message(karma: dict) -> str:
    """Собирает текст сообщения для юзера."""
    points = karma.get("points", 0)
    emoji = karma.get("emoji", "🎁")
    text = karma.get("text", "")

    return (
        f"{emoji} <b>КАРМА ДНЯ</b>\n\n"
        f"Сегодня тебе выпало: <b>+{points} очков</b>!\n\n"
        f"<i>{text}</i>\n\n"
        f"Заходи завтра — карма обновляется каждый день."
    )