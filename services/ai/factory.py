from services.ai.base import AIProvider
from services.ai.gigachat import GigaChatProvider

_provider: AIProvider | None = None


def get_ai_provider() -> AIProvider:
    global _provider
    if _provider is None:
        _provider = GigaChatProvider()
    return _provider