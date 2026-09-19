import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, text

from database.connection import async_session, engine
from database.models import Event, Message, PhotoAnalysis
from utils.logging import get_logger

logger = get_logger(__name__)


# Сколько дней хранить данные
EVENTS_RETENTION_DAYS = 30
MESSAGES_RETENTION_DAYS = 90
PHOTO_ANALYSES_RETENTION_DAYS = 90


async def cleanup_db() -> None:
    """
    Удаляет старые события, сообщения и анализы фото.
    Запускается раз в сутки.
    """
    now = datetime.now(timezone.utc)
    events_cutoff = now - timedelta(days=EVENTS_RETENTION_DAYS)
    messages_cutoff = now - timedelta(days=MESSAGES_RETENTION_DAYS)
    analyses_cutoff = now - timedelta(days=PHOTO_ANALYSES_RETENTION_DAYS)

    events_deleted = 0
    messages_deleted = 0
    analyses_deleted = 0

    try:
        async with async_session() as session:
            # События
            res = await session.execute(
                delete(Event).where(Event.created_at < events_cutoff)
            )
            events_deleted = res.rowcount or 0

            # Сообщения (только старые и прочитанные)
            res = await session.execute(
                delete(Message)
                .where(Message.created_at < messages_cutoff)
                .where(Message.is_read.is_(True))
            )
            messages_deleted = res.rowcount or 0

            # Старые анализы фото (для экономии места)
            res = await session.execute(
                delete(PhotoAnalysis).where(PhotoAnalysis.created_at < analyses_cutoff)
            )
            analyses_deleted = res.rowcount or 0

            await session.commit()

        logger.info(
            f"DB cleanup: events={events_deleted}, "
            f"messages={messages_deleted}, "
            f"analyses={analyses_deleted}"
        )
    except Exception:
        logger.exception("DB cleanup delete failed")
        return

    # VACUUM — освобождаем физическое место (вне транзакции)
    try:
        async with engine.begin() as conn:
            await conn.execute(text("VACUUM events"))
            await conn.execute(text("VACUUM messages"))
            await conn.execute(text("VACUUM photo_analyses"))
        logger.info("VACUUM completed")
    except Exception:
        # VACUUM может не работать внутри транзакций — не критично
        logger.exception("VACUUM failed (не критично)")


async def db_cleanup_loop() -> None:
    """
    Фоновый цикл: раз в сутки чистит БД.
    Первый запуск — через 10 минут после старта.
    """
    # Не сразу после старта, чтобы не мешать загрузке
    await asyncio.sleep(600)

    while True:
        try:
            await cleanup_db()
        except Exception:
            logger.exception("DB cleanup iteration failed")

        # 24 часа
        await asyncio.sleep(24 * 3600)