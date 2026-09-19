from typing import Optional

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest

from utils.logging import get_logger

logger = get_logger(__name__)


async def resolve_channel(bot: Bot, username: str) -> Optional[dict]:
    """
    Пытается получить информацию о канале через Telegram API.
    Возвращает {"title": str, "chat_id": int, "username": str} или None.
    """
    try:
        chat = await bot.get_chat(f"@{username}")
        return {
            "title": chat.title or username,
            "chat_id": chat.id,
            "username": chat.username or username,
            "type": chat.type,
        }
    except TelegramBadRequest as e:
        logger.warning(f"Cannot resolve @{username}: {e}")
        return None
    except Exception as e:
        logger.exception(f"Unexpected error resolving @{username}: {e}")
        return None


async def can_check_subscription(bot: Bot, username: str) -> bool:
    """
    Проверяет, может ли бот видеть подписчиков канала —
    то есть является ли он админом.
    """
    try:
        chat = await bot.get_chat(f"@{username}")
        # Пробуем получить member_count или сделать запрос на себя
        me = await bot.get_me()
        member = await bot.get_chat_member(chat_id=chat.id, user_id=me.id)
        return member.status in ("administrator", "creator")
    except Exception:
        return False