from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update

from services.feature_flags import is_enabled
from utils.logging import get_logger

logger = get_logger(__name__)


class BotEnabledMiddleware(BaseMiddleware):
    """
    Пропускает апдейты только если bot_enabled=true.
    Иначе — молча игнорирует.
    """
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        enabled = await is_enabled("bot_enabled", default=True)
        if not enabled:
            logger.info("Bot disabled by feature flag — update skipped")
            return None
        return await handler(event, data)