from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class AIProvider(ABC):
    """
    Единый интерфейс AI-провайдера.
    """

    @abstractmethod
    async def analyze_photo(
        self,
        image_bytes: bytes,
        prompt_override: Optional[str] = None,
    ) -> Dict[str, Any]:
        ...

    @abstractmethod
    async def generate_daily_result(self, profile: Dict[str, Any]) -> Dict[str, Any]:
        ...

    @abstractmethod
    async def generate_match_description(
        self,
        profile1: Dict[str, Any],
        profile2: Dict[str, Any],
        match_score: int,
    ) -> Dict[str, Any]:
        ...

    @abstractmethod
    async def generate_message_suggestions(
        self,
        my_archetype: str,
        their_archetype: str,
        match_score: int,
        style: str,
    ) -> Dict[str, Any]:
        ...

    @abstractmethod
    async def generate_test_question(
        self,
        test_name: str,
        test_description: str,
    ) -> Dict[str, Any]:
        ...

    @abstractmethod
    async def generate_test_result(
        self,
        test_name: str,
        answers: List[str],
    ) -> Dict[str, Any]:
        ...

    # --------------------------------------------------------
    # Чат
    # --------------------------------------------------------
    @abstractmethod
    async def generate_chat_reply_suggestions(
        self,
        history: List[Dict[str, str]],
        my_name: str,
        other_name: str,
    ) -> Dict[str, Any]:
        ...

    @abstractmethod
    async def analyze_chat(
        self,
        history: List[Dict[str, str]],
        my_name: str,
        other_name: str,
    ) -> Dict[str, Any]:
        ...

    # --------------------------------------------------------
    # Вайб-отчёт (Шаг 1.3)
    # --------------------------------------------------------
    @abstractmethod
    async def generate_vibe_report(
        self,
        profile_data: Dict[str, Any],
        weekly: bool = False,
    ) -> Dict[str, Any]:
        ...

    # --------------------------------------------------------
    # Гороскоп (Этап 2)
    # --------------------------------------------------------
    @abstractmethod
    async def generate_horoscope(
        self,
        profile_data: Dict[str, Any],
    ) -> str:
        ...

    # --------------------------------------------------------
    # Совместимость со звёздами (Этап 3)
    # --------------------------------------------------------
    @abstractmethod
    async def generate_compatibility(
        self,
        profile_data: Dict[str, Any],
        celebrities_text: str,
    ) -> Dict[str, Any]:
        ...

    # --------------------------------------------------------
    # «Какой ты сегодня?» (Этап B)
    # --------------------------------------------------------
    @abstractmethod
    async def generate_today_vibe(
        self,
        profile_data: Dict[str, Any],
        photo_context: str,
    ) -> Dict[str, Any]:
        ...

    # --------------------------------------------------------
    # «Что обо мне думают?» (Этап C)
    # --------------------------------------------------------
    @abstractmethod
    async def generate_first_impression(
        self,
        profile_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Первое впечатление о юзере.

        Возвращает:
            {
                "main_text": str,
                "confidence": int,
                "interest": int,
                "openness": int,
                "hidden_trait": str,       # интрига для Free
                "first_notice": str,       # раскрытие для Pro
                "how_seen": str,           # для Pro
                "improve": str,            # для Pro
            }
        """
        ...