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
    if not text:
        raise ValueError("Empty AI response")

    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)

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
    return "image/jpeg", "jpg"


def _is_retryable_error(exc: Exception) -> bool:
    """
    Проверяем, стоит ли повторять запрос при этой ошибке.
    Повторяем только на 5xx и сетевые проблемы.
    """
    msg = str(exc)
    retryable_markers = (
        " 500 ", " 502 ", " 503 ", " 504 ",
        "Gateway Time-out", "Gateway Timeout",
        "Bad Gateway", "Service Unavailable",
        "Connection", "Timeout", "Read timed out",
        "Temporary failure",
    )
    return any(marker in msg for marker in retryable_markers)


async def _with_retry(coro_func, attempts: int = 3, base_delay: float = 1.0):
    """
    Повторяет асинхронный вызов при retryable-ошибках.
    Паузы: 1s, 2s, 4s...
    """
    last_error: Optional[Exception] = None
    for attempt in range(attempts):
        try:
            return await coro_func()
        except Exception as e:
            last_error = e
            if not _is_retryable_error(e) or attempt == attempts - 1:
                raise
            wait = base_delay * (2 ** attempt)
            logger.warning(
                f"Attempt {attempt + 1}/{attempts} failed "
                f"({e.__class__.__name__}: {str(e)[:120]}). "
                f"Retry in {wait:.1f}s..."
            )
            await asyncio.sleep(wait)

    if last_error:
        raise last_error
    raise RuntimeError("Retry logic error")


# ============================================================
# Провайдер GigaChat
# ============================================================
class GigaChatProvider(AIProvider):
    """
    Реализация AIProvider поверх официального SDK GigaChat.

    - GIGACHAT_MODEL — для текстовых задач.
    - GIGACHAT_VISION_MODEL — для анализа фото.
    """

    def __init__(self) -> None:
        self._client: GigaChat = GigaChat(
            credentials=config.GIGACHAT_API_KEY,
            scope=config.GIGACHAT_SCOPE,
            model=config.GIGACHAT_MODEL,
            verify_ssl_certs=False,
        )
        logger.info(
            f"GigaChat initialized: text_model={config.GIGACHAT_MODEL}, "
            f"vision_model={config.GIGACHAT_VISION_MODEL}"
        )

    # --------------------------------------------------------
    # Низкоуровневый вызов чата (sync → async)
    # --------------------------------------------------------
    async def _chat(
        self,
        messages: List[Messages],
        temperature: float = 0.8,
        max_tokens: int = 1500,
        model: Optional[str] = None,
    ) -> str:
        used_model = model or config.GIGACHAT_MODEL

        def _sync_call() -> str:
            chat_kwargs: Dict[str, Any] = {
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            try:
                chat = Chat(model=used_model, **chat_kwargs)
            except TypeError:
                chat = Chat(**chat_kwargs)

            response = self._client.chat(chat)
            return response.choices[0].message.content

        return await asyncio.to_thread(_sync_call)

    # --------------------------------------------------------
    # Анализ фото (Vision) — с retry
    # --------------------------------------------------------
    async def analyze_photo(
        self,
        image_bytes: bytes,
        prompt_override: Optional[str] = None,
    ) -> Dict[str, Any]:
        mime, ext = _detect_image_mime(image_bytes)
        filename = f"photo.{ext}"

        async def _do_upload():
            def _sync_upload() -> Any:
                buf = io.BytesIO(image_bytes)
                buf.name = filename
                return self._client.upload_file(buf)
            return await asyncio.to_thread(_sync_upload)

        file_obj = await _with_retry(_do_upload, attempts=3, base_delay=1.0)

        logger.info(
            f"Uploaded photo to GigaChat ({mime}, {len(image_bytes)} bytes), "
            f"file_id={file_obj.id_}"
        )

        prompt_text = prompt_override or PHOTO_ANALYSIS_PROMPT
        vision_model = config.GIGACHAT_VISION_MODEL

        messages = [
            Messages(role=MessagesRole.SYSTEM, content=prompt_text),
            Messages(
                role=MessagesRole.USER,
                content="Проанализируй фотографию и верни JSON согласно инструкции.",
                attachments=[file_obj.id_],
            ),
        ]

        logger.info(f"Analyzing photo with Vision model: {vision_model}")

        async def _do_chat() -> str:
            return await self._chat(
                messages,
                temperature=0.9,
                max_tokens=1200,
                model=vision_model,
            )

        raw = await _with_retry(_do_chat, attempts=3, base_delay=1.5)
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