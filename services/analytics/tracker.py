from typing import Any, Optional

from sqlalchemy import select

from database.connection import async_session
from database.models import Event, User
from utils.logging import get_logger

logger = get_logger(__name__)


# ============================================================
# Список допустимых событий.
# Неизвестные имена логируются как WARNING, но всё равно пишутся.
# ============================================================
EVENT_NAMES = {
    # Пользовательские
    "new_users",
    "photo_sent",
    "analysis_started",
    "analysis_completed",
    "second_analysis",

    # Виральность
    "share_clicked",
    "share_generated",
    "referral_opened",
    "referral_completed",

    # Игра
    "game_opt_in",
    "game_opt_out",

    # Поиск / матчи
    "search_used",
    "match_created",
    "block_user",

    # Тесты
    "test_started",
    "test_completed",

    # Монетизация
    "pro_purchase",
    "subscription_offer_shown",
    "subscription_confirmed",
    "ad_shown",
    "ad_clicked",

    # Уведомления
    "daily_sent",
    "chat_reminder_sent",

    # Чат
    "chats_list_viewed",
    "chat_message_sent",
    "chat_ai_sent",
    "chat_ai_analyzed",

    # Старые события (для совместимости, чтобы не терять историю)
    "message_sent",
    "joke_sent",
    "inbox_viewed",
}


# ============================================================
# Запись события
# ============================================================
async def track(
    name: str,
    telegram_id: Optional[int] = None,
    user_id: Optional[int] = None,
    payload: Optional[dict] = None,
) -> None:
    """
    Записывает событие в БД.

    Можно передать либо telegram_id, либо user_id.
    Если только telegram_id — сервис сам подтянет user.id.

    Не падает, если что-то пошло не так — просто логирует.
    """
    if name not in EVENT_NAMES:
        logger.warning(f"Unknown event name: {name}")

    try:
        async with async_session() as session:
            resolved_user_id = user_id

            if resolved_user_id is None and telegram_id is not None:
                row = (await session.execute(
                    select(User.id).where(User.telegram_id == telegram_id)
                )).scalar_one_or_none()
                resolved_user_id = row

            session.add(Event(
                name=name,
                user_id=resolved_user_id,
                telegram_id=telegram_id,
                payload=payload or {},
            ))
            await session.commit()
    except Exception:
        logger.exception(f"Track failed: {name}")


# ============================================================
# Безопасный вызов (не бросает исключений)
# ============================================================
async def track_safe(name: str, **kwargs: Any) -> None:
    """Обёртка, которая гарантированно не падает."""
    try:
        await track(name, **kwargs)
    except Exception:
        pass