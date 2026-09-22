from typing import Dict

from services.analysis.rarity import is_legendary


# ============================================================
# Цветовые темы под архетипы
# ============================================================
THEMES: Dict[str, dict] = {
    # 1. ХАОС
    "chaos": {
        "bg_top": (10, 10, 26),
        "bg_bottom": (42, 10, 58),
        "accent": (255, 46, 136),
        "accent2": (0, 229, 255),
        "text": (245, 245, 250),
        "subtext": (140, 140, 170),
    },
    # 2. СПОКОЙСТВИЕ
    "calm": {
        "bg_top": (8, 20, 24),
        "bg_bottom": (10, 40, 44),
        "accent": (0, 229, 176),
        "accent2": (0, 229, 255),
        "text": (240, 250, 248),
        "subtext": (130, 170, 175),
    },
    # 3. ЛИДЕР
    "leader": {
        "bg_top": (24, 16, 6),
        "bg_bottom": (46, 26, 10),
        "accent": (255, 209, 102),
        "accent2": (255, 140, 66),
        "text": (250, 240, 220),
        "subtext": (190, 165, 120),
    },
    # 4. ИНТЕЛЛЕКТ
    "intellect": {
        "bg_top": (8, 18, 22),
        "bg_bottom": (20, 26, 44),
        "accent": (0, 229, 200),
        "accent2": (168, 85, 247),
        "text": (235, 250, 250),
        "subtext": (140, 175, 190),
    },
    # 5. ЗАГАДКА
    "mystery": {
        "bg_top": (14, 10, 28),
        "bg_bottom": (32, 18, 48),
        "accent": (168, 85, 247),
        "accent2": (100, 116, 139),
        "text": (240, 235, 250),
        "subtext": (150, 140, 175),
    },
    # 6. ЮМОР
    "humor": {
        "bg_top": (26, 20, 8),
        "bg_bottom": (48, 22, 22),
        "accent": (255, 190, 11),
        "accent2": (255, 107, 107),
        "text": (255, 250, 240),
        "subtext": (200, 170, 140),
    },
    # 7. КРЕАТИВ
    "creativity": {
        "bg_top": (20, 10, 30),
        "bg_bottom": (32, 14, 40),
        "accent": (236, 72, 153),
        "accent2": (56, 189, 248),
        "text": (245, 240, 250),
        "subtext": (165, 150, 190),
    },
    # 8. ОПАСНОСТЬ
    "danger": {
        "bg_top": (20, 6, 6),
        "bg_bottom": (40, 10, 10),
        "accent": (255, 51, 85),
        "accent2": (255, 140, 66),
        "text": (255, 245, 245),
        "subtext": (190, 130, 130),
    },
    # 9. ЭНЕРГИЯ
    "energy": {
        "bg_top": (10, 22, 10),
        "bg_bottom": (18, 34, 14),
        "accent": (163, 230, 53),
        "accent2": (250, 204, 21),
        "text": (245, 255, 235),
        "subtext": (160, 190, 130),
    },
    # 10. ХАРИЗМА
    "charisma": {
        "bg_top": (26, 8, 16),
        "bg_bottom": (44, 12, 26),
        "accent": (255, 92, 138),
        "accent2": (255, 158, 92),
        "text": (255, 245, 248),
        "subtext": (190, 145, 165),
    },
    # 11. ЛЕГЕНДАРНЫЙ (золото + янтарь)
    "legendary": {
        "bg_top": (26, 18, 4),
        "bg_bottom": (58, 38, 8),
        "accent": (255, 215, 0),        # чистое золото
        "accent2": (255, 160, 0),       # янтарь
        "text": (255, 250, 235),
        "subtext": (200, 170, 110),
    },
    # 12. ДЕФОЛТ
    "default": {
        "bg_top": (12, 12, 24),
        "bg_bottom": (28, 18, 44),
        "accent": (255, 46, 136),
        "accent2": (0, 229, 255),
        "text": (240, 240, 250),
        "subtext": (150, 150, 175),
    },
}


# ============================================================
# Ключевые слова → тема
# ============================================================
KEYWORDS_TO_THEME = {
    "хаос": "chaos",
    "chaos": "chaos",
    "бардак": "chaos",
    "проблем": "chaos",
    "спокойн": "calm",
    "тих": "calm",
    "уравновеш": "calm",
    "манипул": "calm",
    "лидер": "leader",
    "главн": "leader",
    "вождь": "leader",
    "команд": "leader",
    "интеллект": "intellect",
    "гений": "intellect",
    "умн": "intellect",
    "мозг": "intellect",
    "идеи": "intellect",
    "идея": "intellect",
    "загадоч": "mystery",
    "тайн": "mystery",
    "непонятн": "mystery",
    "скрыт": "mystery",
    "юмор": "humor",
    "смеш": "humor",
    "шутник": "humor",
    "клоун": "humor",
    "весел": "humor",
    "креатив": "creativity",
    "творч": "creativity",
    "художник": "creativity",
    "фантаз": "creativity",
    "опасн": "danger",
    "дерзк": "danger",
    "безрассуд": "danger",
    "риск": "danger",
    "энерг": "energy",
    "актив": "energy",
    "динамич": "energy",
    "харизм": "charisma",
    "магнит": "charisma",
    "звезда": "charisma",
    "притяг": "charisma",
}


def theme_for(archetype: str) -> dict:
    """
    Возвращает тему для архетипа.
    Приоритет: legendary (по точному списку) → keyword → default.
    """
    if is_legendary(archetype):
        return THEMES["legendary"]

    if not archetype:
        return THEMES["default"]

    text = archetype.lower()
    for keyword, theme_name in KEYWORDS_TO_THEME.items():
        if keyword in text:
            return THEMES[theme_name]
    return THEMES["default"]


def theme_name_for(archetype: str) -> str:
    """
    Возвращает имя темы (для отладки / аналитики).
    Приоритет: legendary → keyword → default.
    """
    if is_legendary(archetype):
        return "legendary"

    if not archetype:
        return "default"

    text = archetype.lower()
    for keyword, theme_name in KEYWORDS_TO_THEME.items():
        if keyword in text:
            return theme_name
    return "default"


def tag_for_archetype(archetype: str) -> str:
    """
    Возвращает тег для share-текста.
    Для легендарки — фиксированный #легендарный_вайб.
    Для обычных — первые 1-2 слова архетипа.
    """
    if is_legendary(archetype):
        return "#легендарный_вайб"

    if not archetype:
        return "#вайб"

    words = archetype.split()[:2]
    tag = "_".join(w.lower() for w in words)
    # Убираем всё кроме букв и _
    tag = "".join(c for c in tag if c.isalpha() or c == "_")
    return f"#{tag}" if tag else "#вайб"