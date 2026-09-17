from datetime import datetime

from sqlalchemy import select

from database.connection import async_session
from database.models import User


async def is_premium(telegram_id: int) -> bool:
    async with async_session() as session:
        user = (await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )).scalar_one_or_none()

    if user is None:
        return False
    return bool(user.premium_until and user.premium_until > datetime.utcnow())