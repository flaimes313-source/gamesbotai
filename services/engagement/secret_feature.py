"""
Секретная фича дня (Этап 2).

Логика:
- Юзера не было 2+ дня → шлём ему одну подсказку про фичу.
- Ротация: одна и та же подсказка не повторяется (RewardClaim).
- Отправка через hub (kind="secret_feature", priority=4).

Не пушит активным — только «отсутствующим».
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select

from data.feature_tips import FEATURE_TIPS, all_tip_codes
from database.connection import async_session
from database.models import RewardClaim
from utils.logging import get_logger

logger = get_logger(__name__)


# ============================================================
# КОНСТАНТЫ
# ============================================================
MIN_DAYS_AWAY = 2                 # не был 2+ дня
MAX_DAYS_AWAY = 60                # если пропал больше 2 месяцев — не спамим
REWARD_PREFIX = "tip_seen_"       # префикс RewardClaim для виденных подсказок


# ============================================================
# ПРОВЕРКА: надо ли слать?
# ============================================================
def should_send(last_active_at: Optional[datetime]) -> bool:
    """
    True, если юзера не было MIN_DAYS_AWAY..MAX_DAYS_AWAY дней.
    """
    if last_active_at is None:
        return False

    # Приводим к UTC
    if last_active_at.tzinfo is None:
        last_active_at = last_active_at.replace(tzinfo=timezone.utc)

    now = datetime.now(timezone.utc)
    delta = now - last_active_at

    return (
        timedelta(days=MIN_DAYS_AWAY) <= delta
        <= timedelta(days=MAX_DAYS_AWAY)
    )


# ============================================================
# ВЫБОР ПОДСКАЗКИ
# ============================================================
async def pick_unseen_tip(user_id: int) -> Optional[Dict[str, Any]]:
    """
    Возвращает подсказку, которую юзер ещё не видел.
    Если все видел — сбрасывает историю (начинает заново)
    и возвращает случайную.
    """
    # Достаём список виденных кодов
    try:
        async with async_session() as session:
            rows = (await session.execute(
                select(RewardClaim.reward_code)
                .where(RewardClaim.user_id == user_id)
                .where(RewardClaim.reward_code.like(f"{REWARD_PREFIX}%"))
            )).scalars().all()
            seen_codes = {
                rc.replace(REWARD_PREFIX, "", 1) for rc in rows
            }
    except Exception:
        logger.exception("[TIP] failed to load seen codes")
        seen_codes = set()

    all_codes = all_tip_codes()

    # Невиденные
    unseen = [c for c in all_codes if c not in seen_codes]

    if not unseen:
        # Все видел — сбрасываем историю и берём случайную.
        # Удалять старые RewardClaim не будем (они нужны для UNIQUE),
        # просто вернём случайную из всех. Юзер увидит старую.
        logger.info(f"[TIP] user={user_id} all tips seen, resetting")
        return random.choice(FEATURE_TIPS)

    # Случайная из невиденных
    code = random.choice(unseen)
    for tip in FEATURE_TIPS:
        if tip["code"] == code:
            return tip
    return None


async def mark_tip_seen(user_id: int, code: str) -> bool:
    """
    Помечает подсказку как показанную.
    Возвращает True, если запись создана.
    """
    reward_code = f"{REWARD_PREFIX}{code}"

    try:
        async with async_session() as session:
            claim = RewardClaim(
                user_id=user_id,
                reward_code=reward_code,
                payload={"code": code},
            )
            session.add(claim)
            await session.commit()
        return True
    except Exception:
        # Скорее всего UNIQUE violation — уже видел
        return False


# ============================================================
# ФОРМИРОВАНИЕ СООБЩЕНИЯ
# ============================================================
def format_tip_message(tip: Dict[str, Any]) -> str:
    """
    Собирает текст сообщения для секретной фичи.
    Кратко, с эмодзи, с призывом вернуться.
    """
    emoji = tip.get("emoji", "💡")
    text = tip.get("text", "")
    return (
        f"💡 <b>СЕКРЕТНАЯ ФИЧА ДНЯ</b>\n\n"
        f"{emoji} {text}\n\n"
        f"Возвращайся — тут много всего интересного 👀"
    )


# ============================================================
# ГЛАВНАЯ ФУНКЦИЯ ДЛЯ ПЛАНИРОВЩИКА
# ============================================================
async def prepare_secret_feature(user_id: int) -> Optional[Dict[str, Any]]:
    """
    Готовит payload для hub.schedule_notification.

    Возвращает:
        None — если слать не нужно или нечего.
        dict — {"text": ..., "tip_code": ...} для передачи в hub.

    НЕ помечает подсказку как показанную — это делает воркер
    после успешной отправки (через mark_tip_seen).
    """
    # 1. Есть ли непоказанные подсказки?
    tip = await pick_unseen_tip(user_id)
    if tip is None:
        return None

    # 2. Собираем текст
    text = format_tip_message(tip)

    return {
        "text": text,
        "tip_code": tip["code"],
    }