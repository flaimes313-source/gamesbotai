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
    # НОВЫЕ методы для чата
    # --------------------------------------------------------
    @abstractmethod
    async def generate_chat_reply_suggestions(
        self,
        history: List[Dict[str, str]],
        my_name: str,
        other_name: str,
    ) -> Dict[str, Any]:
        """
        AI-подсказка для ответа в чате.
        history — список сообщений [{"from": "me"|"them", "text": "..."}].
        Возвращает: {"suggestions": ["...", "...", "..."]}
        """
        ...

    @abstractmethod
    async def analyze_chat(
        self,
        history: List[Dict[str, str]],
        my_name: str,
        other_name: str,
    ) -> Dict[str, Any]:
        """
        Анализ переписки.
        Возвращает: {"vibe": str, "mutuality": str, "advice": str, "emoji": str}
        """
        ...

    # --------------------------------------------------------
    # НОВЫЙ метод: Вайб-отчёт (Шаг 1.3)
    # --------------------------------------------------------
    @abstractmethod
    async def generate_vibe_report(
        self,
        profile_data: Dict[str, Any],
        weekly: bool = False,
    ) -> Dict[str, Any]:
        """
        Генерирует персональный вайб-отчёт (Шаг 1.3).

        Параметры:
            profile_data — агрегированные данные юзера:
                {
                    "user": {"first_name": str, "username": Optional[str]},
                    "profiles": [             # все профили юзера (по убыванию даты)
                        {
                            "archetype": str,
                            "scores": {10 ключей: int},
                            "vibe": str,
                            "created_at": ISO-строка,
                        },
                        ...
                    ],
                    "stats": {                # агрегированная статистика
                        "total_analyses": int,
                        "total_points": int,
                        "level": int,
                        "title": str,
                        "current_streak": int,
                        "max_streak": int,
                        "total_messages": int,
                        "total_tests": int,
                        "total_shares": int,
                        "total_referrals": int,
                        "unique_archetypes": int,
                        "legendary_count": int,
                    },
                    "weekly": {               # статистика за 7 дней
                        "active_days": int,   # сколько дней заходил
                        "analyses": int,
                        "messages": int,
                        "shares": int,
                        "tests": int,
                        "points_gained": int,
                        "streak_start": int,  # стрик 7 дней назад
                        "streak_end": int,    # стрик сейчас
                    },
                    "tops": {                 # перцентили (0-100, меньше = лучше)
                        "charisma_pct": int,   # напр. 20 = топ-20%
                        "chaos_pct": int,
                        "humor_pct": int,
                        "points_pct": int,
                    },
                    "recommendations": [       # что предложить юзеру
                        {"type": "test", "code": "test_x", "title": "..."},
                        ...
                    ],
                }
            weekly — True для недельной сводки, False для общего портрета.

        Возвращает:
            {
                "text": str,              # основной текст отчёта (HTML-разметка)
                "summary": str,           # 1-2 строки для картинки (короткий тезис)
                "recommendation": str,    # одна рекомендация
            }
        """
        ...