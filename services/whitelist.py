from datetime import datetime

from sqlalchemy import select

from database.connection import async_session
from database.models import Whitelist
from utils.logging import get_logger

logger = get_logger(__name__)


async def is_whitelisted(telegram_id: int) -> bool:
    async with async_session() as session:
        row = (await session.execute(
            select(Whitelist).where(Whitelist.user_id == telegram_id)
        )).scalar_one_or_none()

    if row is None:
        return False

    # Проверка срока
    if row.expires_at and row.expires_at < datetime.utcnow():
        return False

    return True


async def add_to_whitelist(
    telegram_id: int,
    reason: str | None = None,
    added_by: int | None = None,
) -> None:
    async with async_session() as session:
        existing = (await session.execute(
            select(Whitelist).where(Whitelist.user_id == telegram_id)
        )).scalar_one_or_none()

        if existing:
            existing.reason = reason or existing.reason
            existing.added_by = added_by or existing.added_by
        else:
            session.add(Whitelist(
                user_id=telegram_id,
                reason=reason,
                added_by=added_by,
            ))
        await session.commit()
        logger.info(f"Whitelist add: {telegram_id}")


async def remove_from_whitelist(telegram_id: int) -> None:
    async with async_session() as session:
        row = (await session.execute(
            select(Whitelist).where(Whitelist.user_id == telegram_id)
        )).scalar_one_or_none()
        if row:
            await session.delete(row)
            await session.commit()
            logger.info(f"Whitelist remove: {telegram_id}")