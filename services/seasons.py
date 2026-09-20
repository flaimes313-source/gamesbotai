"""
Определение текущего сезона.
"""
from datetime import datetime, timezone
from typing import Optional


SEASONS = {
    "halloween": {
        "name": "Хэллоуин",
        "start_month": 10,
        "start_day": 15,
        "end_month": 11,
        "end_day": 5,
        "themes": [
            "ПРИЗРАК ХАОСА",
            "ВЕСЁЛЫЙ МОНСТР",
            "ВЕДЬМА-ПЕРФЕКЦИОНИСТКА",
            "ТЫКВЕННЫЙ КОРОЛЬ",
            "ПРИЗРАЧНЫЙ ИНТРОВЕРТ",
        ],
    },
    "new_year": {
        "name": "Новый год",
        "start_month": 12,
        "start_day": 10,
        "end_month": 1,
        "end_day": 15,
        "themes": [
            "СНЕЖНЫЙ ХАОС",
            "ДЕД МОРОЗ ХАРИЗМЫ",
            "САНТА-ХАОС",
            "ЛЕДЯНОЙ ЛИДЕР",
            "ПРАЗДНИЧНЫЙ ПСИХОПАТ",
        ],
    },
    "march_8": {
        "name": "8 марта",
        "start_month": 3,
        "start_day": 1,
        "end_month": 3,
        "end_day": 10,
        "themes": [
            "КОРОЛЕВА ВАЙБА",
            "ЦВЕТОЧНЫЙ ХАОС",
            "ЭЛЕГАНТНЫЙ ЛИДЕР",
        ],
    },
    "feb_23": {
        "name": "23 февраля",
        "start_month": 2,
        "start_day": 15,
        "end_month": 2,
        "end_day": 28,
        "themes": [
            "ГЕНЕРАЛ ХАОСА",
            "БОЕВОЙ ДРУГ",
            "СТРАТЕГ-ИНТРОВЕРТ",
        ],
    },
}


def _date_in_range(now: datetime, season: dict) -> bool:
    """Проверяет, попадает ли дата в диапазон сезона."""
    m, d = now.month, now.day
    sm, sd = season["start_month"], season["start_day"]
    em, ed = season["end_month"], season["end_day"]

    # Простой случай: в одном году
    if sm <= em:
        if sm == em:
            return m == sm and sd <= d <= ed
        return (m == sm and d >= sd) or (m == em and d <= ed) or (sm < m < em)

    # Переход через год (НГ: декабрь-январь)
    return (m == sm and d >= sd) or (m == em and d <= ed) or (m > sm) or (m < em)


def current_season() -> Optional[str]:
    """Возвращает код текущего сезона или None."""
    now = datetime.now(timezone.utc)
    for code, season in SEASONS.items():
        if _date_in_range(now, season):
            return code
    return None


def season_themes() -> list:
    """Список сезонных архетипов для промта (или пустой)."""
    code = current_season()
    if not code:
        return []
    return SEASONS[code].get("themes", [])


def season_name() -> Optional[str]:
    code = current_season()
    return SEASONS[code]["name"] if code else None