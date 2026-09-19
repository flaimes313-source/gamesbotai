from typing import Any, Dict, Optional

from services.ai.factory import get_ai_provider
from services.analysis.scoring import clamp_scores
from utils.logging import get_logger

logger = get_logger(__name__)


async def analyze_photo(
    image_bytes: bytes,
    prompt_override: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Обёртка над AI-провайдером: фото → нормализованный профиль.
    """
    provider = await get_ai_provider()
    result = await provider.analyze_photo(image_bytes, prompt_override=prompt_override)
    result = clamp_scores(result)
    logger.info(f"Analysis done: archetype={result.get('archetype')}")
    return result