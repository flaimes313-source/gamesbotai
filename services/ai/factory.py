from services.ai.base import AIProvider
from services.ai.gigachat import GigaChatProvider
from services.feature_flags import is_enabled
from utils.logging import get_logger

logger = get_logger(__name__)

_provider: AIProvider | None = None


async def get_ai_provider() -> AIProvider:
    """
    Возвращает AI-провайдер. Бросает RuntimeError, если AI отключён флагом.
    """
    if not await is_enabled("ai_enabled", default=True):
        raise RuntimeError("AI disabled by feature flag 'ai_enabled'")

    global _provider
    if _provider is None:
        _provider = GigaChatProvider()
        logger.info("AI provider: GigaChat")
    return _provider


def set_ai_provider(provider: AIProvider) -> None:
    global _provider
    _provider = provider
    logger.info(f"AI provider switched to: {provider.__class__.__name__}")