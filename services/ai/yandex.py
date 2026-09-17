import asyncio
import json
import re
from typing import Any, Dict, List, Optional

import aiohttp

from config import config
from prompts.daily_result import DAILY_RESULT_PROMPT
from prompts.match_description import MATCH_DESCRIPTION_PROMPT
from prompts.message_helper import MESSAGE_HELPER_PROMPT
from prompts.photo_analysis import PHOTO_ANALYSIS_PROMPT
from prompts.test_question import TEST_QUESTION_PROMPT
from prompts.test_result import TEST_RESULT_PROMPT
from services.ai.base import AIProvider
from utils.logging import get_logger

logger = get_logger(__name__)


def _extract_json(text: str) -> Dict[str, Any]:
    if not text:
        raise ValueError("Empty AI response")

    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError(f"No JSON found: {cleaned[:200]}")

    return json.loads(cleaned[start : end + 1])


class YandexGPTProvider(AIProvider):
    """
    Заглушка-реализация AIProvider для YandexGPT.
    Для использования достаточно прописать:
    - YANDEX_FOLDER_ID
    - YANDEX_API_KEY
    и заменить в factory.py.
    """

    def __init__(self) -> None:
        self._folder_id = config.YANDEX_FOLDER_ID
        self._api_key = config.YANDEX_API_KEY
        self._model = config.YANDEX_MODEL

    async def _chat(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.8,
        max_tokens: int = 1500,
    ) -> str:
        url = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Api-Key {self._api_key}",
        }

        payload = {
            "modelUri": f"gpt://{self._folder_id}/{self._model}",
            "completionOptions": {
                "stream": False,
                "temperature": temperature,
                "maxTokens": str(max_tokens),
            },
            "messages": [
                {"role": "system", "text": system_prompt},
                {"role": "user", "text": user_prompt},
            ],
        }

        async with aiohttp.ClientSession() as http:
            async with http.post(url, headers=headers, json=payload, timeout=60) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    raise RuntimeError(f"YandexGPT error {resp.status}: {body[:300]}")
                data = await resp.json()

        return data["result"]["alternatives"][0]["message"]["text"]

    async def analyze_photo(
        self,
        image_bytes: bytes,
        prompt_override: Optional[str] = None,
    ) -> Dict[str, Any]:
        # YandexGPT пока не поддерживает Vision через этот endpoint —
        # бросаем NotImplementedError, чтобы factory переключился или
        # чтобы пользователь явно знал.
        raise NotImplementedError(
            "YandexGPT Vision не реализован в этой версии. "
            "Используйте GigaChat для анализа фото."
        )

    async def generate_daily_result(self, profile: Dict[str, Any]) -> Dict[str, Any]:
        prompt = DAILY_RESULT_PROMPT.format(
            archetype=profile.get("archetype", ""),
            charisma=profile.get("charisma", 0),
            humor=profile.get("humor", 0),
            energy=profile.get("energy", 0),
            chaos=profile.get("chaos", 0),
            creativity=profile.get("creativity", 0),
        )
        raw = await self._chat(prompt, "Сгенерируй результат и верни JSON.", 0.9, 400)
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
        raw = await self._chat(prompt, "Верни только JSON.", 0.9, 500)
        return _extract_json(raw)

    async def generate_message_suggestions(
        self, my_archetype: str, their_archetype: str, match_score: int, style: str
    ) -> Dict[str, Any]:
        prompt = MESSAGE_HELPER_PROMPT.format(
            my_archetype=my_archetype,
            their_archetype=their_archetype,
            match_score=match_score,
            style=style,
        )
        raw = await self._chat(prompt, "Верни только JSON.", 0.9, 500)
        return _extract_json(raw)

    async def generate_test_question(
        self, test_name: str, test_description: str
    ) -> Dict[str, Any]:
        prompt = TEST_QUESTION_PROMPT.format(
            test_name=test_name, test_description=test_description or ""
        )
        raw = await self._chat(prompt, "Верни только JSON.", 0.9, 500)
        return _extract_json(raw)

    async def generate_test_result(
        self, test_name: str, answers: List[str]
    ) -> Dict[str, Any]:
        answers_text = "\n".join(f"- {a}" for a in answers)
        prompt = TEST_RESULT_PROMPT.format(test_name=test_name, answers=answers_text)
        raw = await self._chat(prompt, "Верни только JSON.", 0.9, 500)
        return _extract_json(raw)