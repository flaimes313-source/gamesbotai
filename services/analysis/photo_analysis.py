from typing import Any, Dict

from services.ai.factory import get_ai_provider
from services.analysis.scoring import clamp_scores
from utils.logging import get_logger

logger = get_logger(__name__)


async def analyze_photo(image_bytes: bytes) -> Dict[str, Any]:
    provider = get_ai_provider()
    result = await provider.analyze_photo(image_bytes)
    result = clamp_scores(result)
    logger.info(f"Analysis done: archetype={result.get('archetype')}")
    return result