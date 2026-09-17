from datetime import datetime

from sqlalchemy import select

from database.connection import async_session
from database.models import AIUsage
from services.premium import is_premium
from utils.logging import get_logger

logger = get_logger(__name__)


# Суточные лимиты AI-запросов
FREE_DAILY_LIMIT = 5
PRO_DAILY_LIMIT = 50


def _today_start() -> datetime:
    now = datetime.utcnow()
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


async def check_and_increment(telegram_id: int, user_id: int) -> tuple[bool, int, int]:
    """
    Проверяет лимит и увеличивает счётчик.
    Возвращает: (allowed, current_count, limit)
    """
    premium = await is_premium(telegram_id)
    limit = PRO_DAILY_LIMIT if premium else FREE_DAILY_LIMIT

    today = _today_start()

    async with async_session() as session:
        row = (await session.execute(
            select(AIUsage).where(
                AIUsage.user_id == user_id,
                AIUsage.day == today,
            )
        )).scalar_one_or_none()

        if row is None:
            row = AIUsage(user_id=user_id, day=today, count=0)
            session.add(row)
            await session.flush()

        if row.count >= limit:
            return False, row.count, limit

        row.count += 1
        await session.commit()
        return True, row.count, limit


async def get_remaining(telegram_id: int, user_id: int) -> tuple[int, int]:
    """Сколько AI-запросов осталось (remaining, limit)."""
    premium = await is_premium(telegram_id)
    limit = PRO_DAILY_LIMIT if premium else FREE_DAILY_LIMIT

    today = _today_start()

    async with async_session() as session:
        row = (await session.execute(
            select(AIUsage).where(
                AIUsage.user_id == user_id,
                AIUsage.day == today,
            )
        )).scalar_one_or_none()

    used = row.count if row else 0
    return max(0, limit - used), limit