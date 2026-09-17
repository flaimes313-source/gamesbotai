from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest

from services.whitelist import is_whitelisted


async def is_subscribed(bot: Bot, user_id: int, channel_id: str) -> bool:
    """
    Проверяет, подписан ли пользователь на канал.

    Если пользователь в whitelist — возвращает True всегда
    (то есть для этих пользователей обязательные подписки не требуются).
    """
    # Whitelist — пропускает без подписки
    if await is_whitelisted(user_id):
        return True

    try:
        member = await bot.get_chat_member(chat_id=channel_id, user_id=user_id)
        return member.status in ("member", "administrator", "creator")
    except TelegramBadRequest:
        return False