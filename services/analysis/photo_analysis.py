from typing import Any, Dict, Optional

from services.ai.factory import get_ai_provider
from services.analysis.scoring import clamp_scores
from services.seasons import season_name, season_themes
from utils.logging import get_logger

logger = get_logger(__name__)


async def analyze_photo(
    image_bytes: bytes,
    prompt_override: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Обёртка над AI-провайдером: фото → нормализованный профиль.
    Добавляет сезонный контекст в промт.
    """
    # Сезонный блок промта
    season_block = ""
    themes = season_themes()
    if themes:
        sn = season_name() or "событие"
        themes_str = ", ".join(f'"{t}"' for t in themes)
        season_block = (
            f"\n\nСЕЗОННОЕ СОБЫТИЕ: {sn}!\n"
            f"Постарайся выбрать архетип из сезонных вариантов "
            f"или создай похожий по духу: {themes_str}\n"
            f"Также можно стилизовать short_description под сезон."
        )

    final_prompt = (prompt_override or "") + season_block if prompt_override else None

    provider = await get_ai_provider()
    result = await provider.analyze_photo(image_bytes, prompt_override=final_prompt)
    result = clamp_scores(result)
    logger.info(f"Analysis done: archetype={result.get('archetype')} season={season_name()}")
    return result