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
        """
        Генерирует короткий шутливый гороскоп.

        profile_data:
            {
                "user_name": str,
                "archetype": str,
                "vibe": str,
                "chaos": int,
                "charisma": int,
                "humor": int,
                "energy": int,
                "intellect": int,
                "current_streak": int,
                "level": int,
                "level_title": str,
            }

        Возвращает строку (готовый HTML-текст гороскопа).
        """
        ...