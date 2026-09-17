import asyncio
import io
import json
import re
from typing import Any, Dict, List, Optional

from gigachat import GigaChat
from gigachat.models import Chat, Messages, MessagesRole

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


# ============================================================
# Утилиты
# ============================================================
def _extract_json(text: str) -> Dict[str, Any]:
    """
    Достаём JSON из ответа модели, даже если она обернула его в ```json ... ```.
    Бросает ValueError, если JSON не найден.
    """
    if not text:
        raise ValueError("Empty AI response")

    cleaned = text.strip()

    # Убираем markdown-обёртки
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    # Ищем первый { и последний }
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError(f"No JSON found in AI response: {cleaned[:200]}")

    json_str = cleaned[start : end + 1]

    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error: {e}. Raw: {json_str[:300]}")
        raise


def _detect_image_mime(image_bytes: bytes) -> tuple[str, str]:
    """
    Определяем MIME по magic bytes.
    Возвращает (mime, extension).
    """
    if image_bytes[:3] == b"\xff\xd8\xff":
        return "image/jpeg", "jpg"
    if image_bytes[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png", "png"
    if image_bytes[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif", "gif"
    if image_bytes[:2] == b"BM":
        return "image/bmp", "bmp"
    if image_bytes[:4] == b"RIFF" and image_bytes[8:12] == b"WEBP":
        return "image/webp", "webp"
    # fallback — Telegram шлёт JPEG
    return "image/jpeg", "jpg"


# ============================================================
# Провайдер GigaChat
# ============================================================
class GigaChatProvider(AIProvider):
    """Реализация AIProvider поверх официального SDK GigaChat."""

    def __init__(self) -> None:
        self._client: GigaChat = GigaChat(
            credentials=config.GIGACHAT_API_KEY,
            scope=config.GIGACHAT_SCOPE,
            model=config.GIGACHAT_MODEL,
            verify_ssl_certs=False,
        )

    # --------------------------------------------------------
    # Низкоуровневый вызов чата (sync → async)
    # --------------------------------------------------------
    async def _chat(
        self,
        messages: List[Messages],
        temperature: float = 0.8,
        max_tokens: int = 1500,
    ) -> str:
        def _sync_call() -> str:
            response = self._client.chat(
                Chat(
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
            )
            return response.choices[0].message.content

        return await asyncio.to_thread(_sync_call)

    # --------------------------------------------------------
    # Анализ фото (Vision)
    # --------------------------------------------------------
    async def analyze_photo(
        self,
        image_bytes: bytes,
        prompt_override: Optional[str] = None,
    ) -> Dict[str, Any]:
        # Явно определяем формат
        mime, ext = _detect_image_mime(image_bytes)
        filename = f"photo.{ext}"

        def _upload() -> Any:
            """
            GigaChat SDK определяет MIME по имени файла.
            Передаём BytesIO с атрибутом .name = "photo.jpg".
            """
            buf = io.BytesIO(image_bytes)
            buf.name = filename
            return self._client.upload_file(buf)

        file_obj = await asyncio.to_thread(_upload)
        logger.info(
            f"Uploaded photo to GigaChat ({mime}, {len(image_bytes)} bytes), "
            f"file_id={file_obj.id_}"
        )

        prompt_text = prompt_override or PHOTO_ANALYSIS_PROMPT

        messages = [
            Messages(
                role=MessagesRole.SYSTEM,
                content=prompt_text,
            ),
            Messages(
                role=MessagesRole.USER,
                content="Проанализируй фотографию и верни JSON согласно инструкции.",
                attachments=[file_obj.id_],
            ),
        ]

        raw = await self._chat(messages, temperature=0.9, max_tokens=1200)
        logger.info(f"GigaChat photo analysis raw: {raw[:300]}")
        return _extract_json(raw)

    # --------------------------------------------------------
    # Ежедневный результат
    # --------------------------------------------------------
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
        raw = await self._chat(messages, temperature=0.9, max_tokens=400)
        return _extract_json(raw)

    # --------------------------------------------------------
    # Описание Match
    # --------------------------------------------------------
    async def generate_match_description(
        self,
        profile1: Dict[str, Any],
        profile2: Dict[str, Any],
        match_score: int,
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
        raw = await self._chat(messages, temperature=0.9, max_tokens=500)
        return _extract_json(raw)

    # --------------------------------------------------------
    # Варианты первого сообщения
    # --------------------------------------------------------
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
        raw = await self._chat(messages, temperature=0.9, max_tokens=500)
        return _extract_json(raw)

    # --------------------------------------------------------
    # Вопрос теста
    # --------------------------------------------------------
    async def generate_test_question(
        self,
        test_name: str,
        test_description: str,
    ) -> Dict[str, Any]:
        prompt = TEST_QUESTION_PROMPT.format(
            test_name=test_name,
            test_description=test_description or "",
        )
        messages = [Messages(role=MessagesRole.SYSTEM, content=prompt)]
        raw = await self._chat(messages, temperature=0.9, max_tokens=500)
        return _extract_json(raw)

    # --------------------------------------------------------
    # Результат теста
    # --------------------------------------------------------
    async def generate_test_result(
        self,
        test_name: str,
        answers: List[str],
    ) -> Dict[str, Any]:
        answers_text = "\n".join(f"- {a}" for a in answers)
        prompt = TEST_RESULT_PROMPT.format(
            test_name=test_name,
            answers=answers_text,
        )
        messages = [Messages(role=MessagesRole.SYSTEM, content=prompt)]
        raw = await self._chat(messages, temperature=0.9, max_tokens=500)
        return _extract_json(raw)