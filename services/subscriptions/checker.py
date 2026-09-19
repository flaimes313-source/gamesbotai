from typing import Optional

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest

from services.whitelist import is_whitelisted


async def is_subscribed(
    bot: Optional[Bot],
    user_id: int,
    channel_id: str,
) -> bool:
    """
    Проверяет, подписан ли пользователь на канал.

    - Whitelist → всегда True.
    - Если bot is None → False (нет возможности проверить).
    """
    if await is_whitelisted(user_id):
        return True

    if bot is None:
        return False

    try:
        member = await bot.get_chat_member(chat_id=channel_id, user_id=user_id)
        return member.status in ("member", "administrator", "creator")
    except TelegramBadRequest:
        return False