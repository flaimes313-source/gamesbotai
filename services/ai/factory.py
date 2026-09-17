from services.ai.base import AIProvider
from services.ai.gigachat import GigaChatProvider
from utils.logging import get_logger

logger = get_logger(__name__)

_provider: AIProvider | None = None


def get_ai_provider() -> AIProvider:
    global _provider
    if _provider is None:
        _provider = GigaChatProvider()
        logger.info("AI provider: GigaChat")
    return _provider


def set_ai_provider(provider: AIProvider) -> None:
    """Для тестов или замены на YandexGPT."""
    global _provider
    _provider = provider
    logger.info(f"AI provider switched to: {provider.__class__.__name__}")