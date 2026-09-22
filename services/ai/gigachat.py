import asyncio
import io
import json
import re
from typing import Any, Dict, List, Optional

from gigachat import GigaChat
from gigachat.models import Chat, Messages, MessagesRole

from config import config
from prompts.chat_helper import CHAT_ANALYSIS_PROMPT, CHAT_REPLY_PROMPT
from prompts.daily_result import DAILY_RESULT_PROMPT
from prompts.match_description import MATCH_DESCRIPTION_PROMPT
from prompts.message_helper import MESSAGE_HELPER_PROMPT
from prompts.photo_analysis import PHOTO_ANALYSIS_PROMPT
from prompts.test_question import TEST_QUESTION_PROMPT
from prompts.test_result import TEST_RESULT_PROMPT
from prompts.vibe_report import VIBE_REPORT_PROMPT, VIBE_WEEKLY_PROMPT
from services.ai.base import AIProvider
from utils.logging import get_logger

logger = get_logger(__name__)


# ============================================================
# Утилиты: определение MIME по magic bytes
# ============================================================
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
    # fallback — Telegram по умолчанию шлёт JPEG
    return "image/jpeg", "jpg"


# ============================================================
# Утилиты: устойчивый парсинг JSON
# ============================================================
def _try_fix_json(text: str) -> str:
    """
    Автопочинка частых ошибок LLM в JSON:

    1. Пропущенная запятая между двумя строками в массиве.
    2. Висящая запятая перед закрывающей скобкой.
    3. Одинарные кавычки вокруг ключей/значений (простой случай).
    """
    s = text

    # 1. Убираем висящие запятые перед ] или }
    s = re.sub(r",(\s*[}\]])", r"\1", s)

    # 2. Добавляем запятую между двумя строками в массиве.
    s = re.sub(r'"\s*\n\s*"', '",\n    "', s)

    # 3. Иногда пропущена запятая в одной строке: "...текст" "текст..."
    s = re.sub(r'"\s+"', '", "', s)

    return s


def _extract_json(text: str) -> Dict[str, Any]:
    """
    Достаём JSON из ответа модели.
    Пробуем несколько стратегий:
    1. Как есть.
    2. Отрезаем первый {...} блок и парсим.
    3. Пробуем починить типичные ошибки и парсить снова.
    """
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

    # Попытка 1: как есть
    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e1:
        logger.warning(f"[JSON] First parse failed: {e1}. Trying to fix…")

    # Попытка 2: автопочинка
    fixed = _try_fix_json(json_str)
    try:
        return json.loads(fixed)
    except json.JSONDecodeError as e2:
        logger.error(f"[JSON] Fix attempt failed: {e2}. Raw: {json_str[:400]}")
        raise ValueError(
            f"Could not parse AI JSON after fix: {e2}. "
            f"Raw preview: {json_str[:200]}"
        )


# ============================================================
# Утилита: разбор текстового ответа вайб-отчёта
# ============================================================
def _parse_vibe_report_text(raw: str) -> Dict[str, str]:
    """
    GigaChat для вайб-отчёта возвращает ТЕКСТ (не JSON).
    Формат ответа промта:

        [SUMMARY]
        короткая фраза для картинки

        [REPORT]
        основной текст отчёта

        [RECOMMENDATION]
        одна рекомендация
    """
    text = (raw or "").strip()

    summary = ""
    report = text
    recommendation = ""

    # [SUMMARY]
    m = re.search(r"\[SUMMARY\]\s*(.+?)(?=\n\s*\[|\Z)", text, re.DOTALL | re.IGNORECASE)
    if m:
        summary = m.group(1).strip()

    # [REPORT]
    m = re.search(r"\[REPORT\]\s*(.+?)(?=\n\s*\[|\Z)", text, re.DOTALL | re.IGNORECASE)
    if m:
        report = m.group(1).strip()

    # [RECOMMENDATION]
    m = re.search(r"\[RECOMMENDATION\]\s*(.+?)(?=\n\s*\[|\Z)", text, re.DOTALL | re.IGNORECASE)
    if m:
        recommendation = m.group(1).strip()

    # Fallback: если ни один маркер не найден — считаем весь текст отчётом
    if not summary and not report and not recommendation:
        report = text

    # Если summary пуст — берём первое предложение отчёта
    if not summary and report:
        first_sentence = re.split(r"[.!?]\s", report, maxsplit=1)[0]
        summary = (first_sentence[:120] + "…") if len(first_sentence) > 120 else first_sentence

    return {
        "text": report,
        "summary": summary,
        "recommendation": recommendation,
    }


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
        logger.info(
            f"GigaChat initialized: text_model={config.GIGACHAT_MODEL}, "
            f"vision_model={config.GIGACHAT_VISION_MODEL}"
        )

    # --------------------------------------------------------
    # Низкоуровневый вызов чата
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
    # Утилита: вызов с retry на битый JSON
    # --------------------------------------------------------
    async def _chat_json(
        self,
        messages: List[Messages],
        temperature_first: float = 0.7,
        temperature_retry: float = 0.3,
        max_tokens: int = 500,
        model: Optional[str] = None,
        log_tag: str = "JSON",
    ) -> Dict[str, Any]:
        """
        Двухэтапный вызов:
        1. temperature_first → парсим JSON.
        2. Если не получилось — temperature_retry (ниже) → парсим JSON.
        """
        # Попытка 1
        try:
            raw = await self._chat(
                messages,
                temperature=temperature_first,
                max_tokens=max_tokens,
                model=model,
            )
            return _extract_json(raw)
        except Exception as e1:
            logger.warning(f"[{log_tag}] Attempt 1 failed: {e1}. Retrying with temp={temperature_retry}…")

        # Попытка 2
        raw = await self._chat(
            messages,
            temperature=temperature_retry,
            max_tokens=max_tokens,
            model=model,
        )
        return _extract_json(raw)

    # --------------------------------------------------------
    # Анализ фото (Vision)
    # --------------------------------------------------------
    async def analyze_photo(
        self,
        image_bytes: bytes,
        prompt_override: Optional[str] = None,
    ) -> Dict[str, Any]:
        mime, ext = _detect_image_mime(image_bytes)
        filename = f"photo.{ext}"

        def _upload() -> Any:
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
            Messages(role=MessagesRole.SYSTEM, content=prompt_text),
            Messages(
                role=MessagesRole.USER,
                content="Проанализируй фотографию и верни JSON согласно инструкции.",
                attachments=[file_obj.id_],
            ),
        ]

        vision_model = config.GIGACHAT_VISION_MODEL
        logger.info(f"Analyzing photo with Vision model: {vision_model}")

        raw = await self._chat(
            messages,
            temperature=0.9,
            max_tokens=1200,
            model=vision_model,
        )
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
        return await self._chat_json(
            messages,
            temperature_first=0.9,
            temperature_retry=0.4,
            max_tokens=400,
            log_tag="DAILY",
        )

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
        return await self._chat_json(
            messages,
            temperature_first=0.9,
            temperature_retry=0.4,
            max_tokens=500,
            log_tag="MATCH",
        )

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
        return await self._chat_json(
            messages,
            temperature_first=0.9,
            temperature_retry=0.4,
            max_tokens=500,
            log_tag="MSG_HELPER",
        )

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
        return await self._chat_json(
            messages,
            temperature_first=0.9,
            temperature_retry=0.4,
            max_tokens=500,
            log_tag="TEST_Q",
        )

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
        return await self._chat_json(
            messages,
            temperature_first=0.9,
            temperature_retry=0.4,
            max_tokens=500,
            log_tag="TEST_R",
        )

    # --------------------------------------------------------
    # AI-подсказки для ответа в чате (PRO)
    # --------------------------------------------------------
    async def generate_chat_reply_suggestions(
        self,
        history: List[Dict[str, str]],
        my_name: str,
        other_name: str,
    ) -> Dict[str, Any]:
        if not history:
            history_text = "(пока нет сообщений)"
        else:
            lines = []
            for m in history[-5:]:
                prefix = f"{my_name}:" if m["from"] == "me" else f"{other_name}:"
                lines.append(f"{prefix} {m['text']}")
            history_text = "\n".join(lines)

        prompt = CHAT_REPLY_PROMPT.format(
            my_name=my_name,
            other_name=other_name,
            history=history_text,
        )
        messages = [Messages(role=MessagesRole.SYSTEM, content=prompt)]
        return await self._chat_json(
            messages,
            temperature_first=0.7,
            temperature_retry=0.3,
            max_tokens=600,
            log_tag="CHAT_REPLY",
        )

    # --------------------------------------------------------
    # Анализ переписки (PRO)
    # --------------------------------------------------------
    async def analyze_chat(
        self,
        history: List[Dict[str, str]],
        my_name: str,
        other_name: str,
    ) -> Dict[str, Any]:
        if not history:
            history_text = "(пока нет сообщений)"
        else:
            lines = []
            for m in history[-15:]:
                prefix = f"{my_name}:" if m["from"] == "me" else f"{other_name}:"
                lines.append(f"{prefix} {m['text']}")
            history_text = "\n".join(lines)

        prompt = CHAT_ANALYSIS_PROMPT.format(
            my_name=my_name,
            other_name=other_name,
            history=history_text,
        )
        messages = [Messages(role=MessagesRole.SYSTEM, content=prompt)]
        return await self._chat_json(
            messages,
            temperature_first=0.7,
            temperature_retry=0.3,
            max_tokens=500,
            log_tag="CHAT_ANALYZE",
        )

    # --------------------------------------------------------
    # Вайб-отчёт (Шаг 1.3)
    # --------------------------------------------------------
    async def generate_vibe_report(
        self,
        profile_data: Dict[str, Any],
        weekly: bool = False,
    ) -> Dict[str, Any]:
        """
        Генерирует персональный вайб-отчёт.

        weekly=False → портрет (по запросу из профиля).
        weekly=True  → сводка за неделю (для авто-рассылки).

        Возвращает: {"text": str, "summary": str, "recommendation": str}.
        GigaChat возвращает ТЕКСТ (не JSON), разбираем по маркерам
        [SUMMARY], [REPORT], [RECOMMENDATION].
        """
        user = profile_data.get("user", {})
        profiles = profile_data.get("profiles", []) or []
        stats = profile_data.get("stats", {}) or {}
        weekly_data = profile_data.get("weekly", {}) or {}
        tops = profile_data.get("tops", {}) or {}
        recommendations = profile_data.get("recommendations", []) or []

        # --- Профили: список архетипов + характеристики ---
        profiles_lines = []
        for p in profiles[:10]:  # не больше 10 последних — иначе промт раздуется
            arch = p.get("archetype", "")
            scores = p.get("scores", {}) or {}
            scores_str = ", ".join(
                f"{k}={v}" for k, v in scores.items() if isinstance(v, int)
            )
            vibe = p.get("vibe", "")
            profiles_lines.append(
                f"- «{arch}» ({vibe}) [{scores_str}]"
            )
        profiles_text = "\n".join(profiles_lines) if profiles_lines else "(нет)"

        # --- Топы ---
        tops_lines = []
        if tops.get("charisma_pct") is not None:
            tops_lines.append(f"харизма — топ-{tops['charisma_pct']}%")
        if tops.get("chaos_pct") is not None:
            tops_lines.append(f"хаос — топ-{tops['chaos_pct']}%")
        if tops.get("humor_pct") is not None:
            tops_lines.append(f"юмор — топ-{tops['humor_pct']}%")
        if tops.get("points_pct") is not None:
            tops_lines.append(f"очки — топ-{tops['points_pct']}%")
        tops_text = "; ".join(tops_lines) if tops_lines else "нет данных"

        # --- Рекомендации (что предложить юзеру) ---
        recs_lines = []
        for r in recommendations[:3]:
            title = r.get("title", "")
            rtype = r.get("type", "")
            if title:
                recs_lines.append(f"- {rtype}: {title}")
        recs_text = "\n".join(recs_lines) if recs_lines else "(нет)"

        # --- Промт ---
        template = VIBE_WEEKLY_PROMPT if weekly else VIBE_REPORT_PROMPT

        prompt = template.format(
            user_name=user.get("first_name", "Игрок"),
            user_username=user.get("username") or "",
            total_analyses=stats.get("total_analyses", 0),
            total_points=stats.get("total_points", 0),
            level=stats.get("level", 1),
            level_title=stats.get("title", ""),
            current_streak=stats.get("current_streak", 0),
            max_streak=stats.get("max_streak", 0),
            total_messages=stats.get("total_messages", 0),
            total_tests=stats.get("total_tests", 0),
            total_shares=stats.get("total_shares", 0),
            total_referrals=stats.get("total_referrals", 0),
            unique_archetypes=stats.get("unique_archetypes", 0),
            legendary_count=stats.get("legendary_count", 0),
            profiles_text=profiles_text,
            tops_text=tops_text,
            recommendations_text=recs_text,
            # Недельные метрики
            active_days=weekly_data.get("active_days", 0),
            weekly_analyses=weekly_data.get("analyses", 0),
            weekly_messages=weekly_data.get("messages", 0),
            weekly_shares=weekly_data.get("shares", 0),
            weekly_tests=weekly_data.get("tests", 0),
            weekly_points=weekly_data.get("points_gained", 0),
            streak_start=weekly_data.get("streak_start", 0),
            streak_end=weekly_data.get("streak_end", 0),
        )

        messages = [Messages(role=MessagesRole.SYSTEM, content=prompt)]

        raw = await self._chat(
            messages,
            temperature=0.85,
            max_tokens=1400,
        )
        logger.info(f"[VIBE] raw len={len(raw)} weekly={weekly}")

        parsed = _parse_vibe_report_text(raw)
        logger.info(
            f"[VIBE] parsed: summary_len={len(parsed['summary'])}, "
            f"text_len={len(parsed['text'])}, "
            f"rec_len={len(parsed['recommendation'])}"
        )
        return parsed