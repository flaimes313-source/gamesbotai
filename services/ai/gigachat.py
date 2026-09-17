import asyncio
import json
import re
import uuid
from typing import Any, Dict

from gigachat import GigaChat
from gigachat.models import Chat, Messages, MessagesRole

from config import config
from prompts.daily_result import DAILY_RESULT_PROMPT
from prompts.match_description import MATCH_DESCRIPTION_PROMPT
from prompts.message_helper import MESSAGE_HELPER_PROMPT
from prompts.photo_analysis import PHOTO_ANALYSIS_PROMPT
from services.ai.base import AIProvider
from utils.logging import get_logger

logger = get_logger(__name__)


def _extract_json(text: str) -> Dict[str, Any]:
    """Достаём JSON из ответа модели, даже если она обернула его в ```json ... ```."""
    text = text.strip()

    # Убираем markdown-обёртки
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)

    # Ищем первый { и последний }
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"No JSON found in AI response: {text[:200]}")

    return json.loads(text[start : end + 1])


class GigaChatProvider(AIProvider):
    def __init__(self) -> None:
        self._client = GigaChat(
            credentials=config.GIGACHAT_API_KEY,
            scope=config.GIGACHAT_SCOPE,
            model=config.GIGACHAT_MODEL,
            verify_ssl_certs=False,
        )

    async def _chat(self, messages: list) -> str:
        """Обёртка синхронного SDK в async-вызов."""
        def _sync_call():
            response = self._client.chat(
                Chat(messages=messages, temperature=0.8, max_tokens=1500)
            )
            return response.choices[0].message.content

        return await asyncio.to_thread(_sync_call)

    async def analyze_photo(self, image_bytes: bytes) -> Dict[str, Any]:
        # Загружаем файл в GigaChat
        def _upload():
            return self._client.upload_file(image_bytes)

        file_obj = await asyncio.to_thread(_upload)

        messages = [
            Messages(
                role=MessagesRole.SYSTEM,
                content=PHOTO_ANALYSIS_PROMPT,
            ),
            Messages(
                role=MessagesRole.USER,
                content="Проанализируй фотографию и верни JSON согласно инструкции.",
                attachments=[file_obj.id_],
            ),
        ]

        raw = await self._chat(messages)
        logger.info(f"GigaChat photo analysis raw: {raw[:300]}")
        return _extract_json(raw)

    async def generate_daily_result(self, profile: Dict[str, Any]) -> Dict[str, Any]:
        prompt = DAILY_RESULT_PROMPT.format(
            archetype=profile.get("archetype", ""),
            charisma=profile.get("charisma", 0),
            humor=profile.get("humor", 0),
            energy=profile.get("energy", 0),
            chaos=profile.get("chaos", 0),
            creativity=profile.get("creativity", 0),
        )
        messages = [Messages(role=MessagesRole.SYSTEM, content=prompt)]
        raw = await self._chat(messages)
        return _extract_json(raw)

    async def generate_match_description(
        self, profile1: Dict[str, Any], profile2: Dict[str, Any], match_score: int
    ) -> Dict[str, Any]:
        prompt = MATCH_DESCRIPTION_PROMPT.format(
            archetype1=profile1.get("archetype", ""),
            charisma1=profile1.get("charisma", 0),
            humor1=profile1.get("humor", 0),
            energy1=profile1.get("energy", 0),
            chaos1=profile1.get("chaos", 0),
            intellect1=profile1.get("intellect", 0),
            archetype2=profile2.get("archetype", ""),
            charisma2=profile2.get("charisma", 0),
            humor2=profile2.get("humor", 0),
            energy2=profile2.get("energy", 0),
            chaos2=profile2.get("chaos", 0),
            intellect2=profile2.get("intellect", 0),
            match_score=match_score,
        )
        messages = [Messages(role=MessagesRole.SYSTEM, content=prompt)]
        raw = await self._chat(messages)
        return _extract_json(raw)

    async def generate_message_suggestions(
        self,
        my_archetype: str,
        their_archetype: str,
        match_score: int,
        style: str,
    ) -> Dict[str, Any]:
        prompt = MESSAGE_HELPER_PROMPT.format(
            my_archetype=my_archetype,
            their_archetype=their_archetype,
            match_score=match_score,
            style=style,
        )
        messages = [Messages(role=MessagesRole.SYSTEM, content=prompt)]
        raw = await self._chat(messages)
        return _extract_json(raw)