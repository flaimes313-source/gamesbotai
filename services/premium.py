from datetime import datetime, timezone

from sqlalchemy import select

from database.connection import async_session
from database.models import User


async def is_premium(telegram_id: int) -> bool:
    """
    Проверяет, активна ли PRO у юзера.

    ВАЖНО: premium_until хранится как TIMESTAMPTZ (aware).
    Сравниваем с datetime.now(timezone.utc) (aware).
    """
    async with async_session() as session:
        user = (await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )).scalar_one_or_none()

    if user is None:
        return False
    if not user.premium_until:
        return False

    # Если из БД вернулся naive — приводим к aware UTC
    until = user.premium_until
    if until.tzinfo is None:
        until = until.replace(tzinfo=timezone.utc)

    return until > datetime.now(timezone.utc)