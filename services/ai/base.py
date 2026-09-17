from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class AIProvider(ABC):
    """
    Единый интерфейс AI-провайдера.

    Любая реализация (GigaChat, YandexGPT, локальная модель и т.д.)
    должна реализовывать все эти методы. Это позволяет менять
    провайдера без переписывания бизнес-логики бота.
    """

    @abstractmethod
    async def analyze_photo(
        self,
        image_bytes: bytes,
        prompt_override: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Анализ фотографии.
        Возвращает JSON:
        {
          "archetype": str,
          "short_description": str,
          "scores": {charisma..leadership},
          "funny_trait": str,
          "danger_level": int,
          "friendship_score": int,
          "vibe": str,
          "share_text": str
        }
        """
        ...

    @abstractmethod
    async def generate_daily_result(self, profile: Dict[str, Any]) -> Dict[str, Any]:
        """
        Короткий ежедневный игровой результат.
        Возвращает: {"title": str, "text": str, "emoji": str}
        """
        ...

    @abstractmethod
    async def generate_match_description(
        self,
        profile1: Dict[str, Any],
        profile2: Dict[str, Any],
        match_score: int,
    ) -> Dict[str, Any]:
        """
        Описание игрового совпадения.
        Возвращает: {"headline": str, "description": str, "chaos_comment": str}
        """
        ...

    @abstractmethod
    async def generate_message_suggestions(
        self,
        my_archetype: str,
        their_archetype: str,
        match_score: int,
        style: str,
    ) -> Dict[str, Any]:
        """
        Варианты первого сообщения.
        Возвращает: {"messages": [str, str, str]}
        """
        ...

    @abstractmethod
    async def generate_test_question(
        self,
        test_name: str,
        test_description: str,
    ) -> Dict[str, Any]:
        """
        Вопрос теста с вариантами.
        Возвращает: {"question": str, "options": [str, str, str, str]}
        """
        ...

    @abstractmethod
    async def generate_test_result(
        self,
        test_name: str,
        answers: List[str],
    ) -> Dict[str, Any]:
        """
        Итог теста.
        Возвращает: {"title": str, "text": str, "emoji": str}
        """
        ...