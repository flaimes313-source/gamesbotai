from typing import Dict


# ============================================================
# Цветовые темы под архетипы
# ============================================================
# Структура темы:
#   bg_top, bg_bottom  — градиент фона
#   accent, accent2    — основные цвета (неоновые)
#   text, subtext      — цвета текста
#   glow               — цвет свечения
#   tag_color          — цвет хештега/плашки
# ============================================================

THEMES: Dict[str, dict] = {
    # 1. ХАОС — неоново-розовый + голубой
    "chaos": {
        "bg_top": (10, 10, 26),
        "bg_bottom": (42, 10, 58),
        "accent": (255, 46, 136),      # #ff2e88
        "accent2": (0, 229, 255),      # #00e5ff
        "text": (245, 245, 250),
        "subtext": (138, 138, 168),
        "glow": (255, 46, 136),
        "tag_color": (255, 46, 136),
    },

    # 2. СПОКОЙНЫЙ — изумрудный + бирюза
    "calm": {
        "bg_top": (8, 20, 24),
        "bg_bottom": (10, 40, 44),
        "accent": (0, 229, 176),       # #00e5b0
        "accent2": (0, 229, 255),      # #00e5ff
        "text": (240, 250, 248),
        "subtext": (130, 170, 175),
        "glow": (0, 229, 176),
        "tag_color": (0, 229, 176),
    },

    # 3. ЛИДЕР — золотой + оранжевый
    "leader": {
        "bg_top": (24, 16, 6),
        "bg_bottom": (46, 26, 10),
        "accent": (255, 209, 102),     # #ffd166
        "accent2": (255, 140, 66),     # #ff8c42
        "text": (250, 240, 220),
        "subtext": (190, 165, 120),
        "glow": (255, 209, 102),
        "tag_color": (255, 209, 102),
    },

    # 4. ИНТЕЛЛЕКТ — мятный + фиолетовый
    "intellect": {
        "bg_top": (8, 18, 22),
        "bg_bottom": (20, 26, 44),
        "accent": (0, 229, 200),       # #00e5c8
        "accent2": (168, 85, 247),     # #a855f7
        "text": (235, 250, 250),
        "subtext": (140, 175, 190),
        "glow": (0, 229, 200),
        "tag_color": (0, 229, 200),
    },

    # 5. ЗАГАДКА — фиолетовый + серо-синий
    "mystery": {
        "bg_top": (14, 10, 28),
        "bg_bottom": (32, 18, 48),
        "accent": (168, 85, 247),      # #a855f7
        "accent2": (100, 116, 139),    # #64748b
        "text": (240, 235, 250),
        "subtext": (150, 140, 175),
        "glow": (168, 85, 247),
        "tag_color": (168, 85, 247),
    },

    # 6. ЮМОР — жёлтый + коралловый
    "humor": {
        "bg_top": (26, 20, 8),
        "bg_bottom": (48, 22, 22),
        "accent": (255, 190, 11),      # #ffbe0b
        "accent2": (255, 107, 107),    # #ff6b6b
        "text": (255, 250, 240),
        "subtext": (200, 170, 140),
        "glow": (255, 190, 11),
        "tag_color": (255, 190, 11),
    },

    # 7. КРЕАТИВ — градиент фиолет-розовый-голубой
    "creativity": {
        "bg_top": (20, 10, 30),
        "bg_bottom": (32, 14, 40),
        "accent": (236, 72, 153),      # #ec4899
        "accent2": (56, 189, 248),     # #38bdf8
        "text": (245, 240, 250),
        "subtext": (165, 150, 190),
        "glow": (236, 72, 153),
        "tag_color": (236, 72, 153),
    },

    # 8. ОПАСНОСТЬ — тёмно-красный + оранжевый
    "danger": {
        "bg_top": (20, 6, 6),
        "bg_bottom": (40, 10, 10),
        "accent": (255, 51, 85),       # #ff3355
        "accent2": (255, 140, 66),     # #ff8c42
        "text": (255, 245, 245),
        "subtext": (190, 130, 130),
        "glow": (255, 51, 85),
        "tag_color": (255, 51, 85),
    },

    # 9. ЭНЕРГИЯ — кислотный зелёный + лайм
    "energy": {
        "bg_top": (10, 22, 10),
        "bg_bottom": (18, 34, 14),
        "accent": (163, 230, 53),      # #a3e635
        "accent2": (250, 204, 21),     # #facc15
        "text": (245, 255, 235),
        "subtext": (160, 190, 130),
        "glow": (163, 230, 53),
        "tag_color": (163, 230, 53),
    },

    # 10. ХАРИЗМА — алый + розовый
    "charisma": {
        "bg_top": (26, 8, 16),
        "bg_bottom": (44, 12, 26),
        "accent": (255, 92, 138),      # #ff5c8a
        "accent2": (255, 158, 92),     # #ff9e5c
        "text": (255, 245, 248),
        "subtext": (190, 145, 165),
        "glow": (255, 92, 138),
        "tag_color": (255, 92, 138),
    },

    # 11. ДЕФОЛТ — универсальная (глубокий фиолет + голубой)
    "default": {
        "bg_top": (12, 12, 24),
        "bg_bottom": (28, 18, 44),
        "accent": (255, 46, 136),      # #ff2e88
        "accent2": (0, 229, 255),      # #00e5ff
        "text": (240, 240, 250),
        "subtext": (150, 150, 175),
        "glow": (255, 46, 136),
        "tag_color": (255, 46, 136),
    },
}


# ============================================================
# Ключевые слова → тема
# ============================================================
KEYWORDS_TO_THEME = {
    # Хаос
    "хаос": "chaos",
    "chaos": "chaos",
    "бардак": "chaos",
    "проблем": "chaos",

    # Спокойствие
    "спокойн": "calm",
    "тих": "calm",
    "уравновеш": "calm",
    "манипул": "calm",

    # Лидер
    "лидер": "leader",
    "главн": "leader",
    "вождь": "leader",
    "команд": "leader",

    # Интеллект
    "интеллект": "intellect",
    "гений": "intellect",
    "умн": "intellect",
    "мозг": "intellect",
    "идеи": "intellect",
    "идея": "intellect",

    # Загадочность
    "загадоч": "mystery",
    "тайн": "mystery",
    "непонятн": "mystery",
    "скрыт": "mystery",

    # Юмор
    "юмор": "humor",
    "смеш": "humor",
    "шутник": "humor",
    "клоун": "humor",
    "весел": "humor",

    # Креатив
    "креатив": "creativity",
    "творч": "creativity",
    "художник": "creativity",
    "фантаз": "creativity",

    # Опасность
    "опасн": "danger",
    "дерзк": "danger",
    "безрассуд": "danger",
    "риск": "danger",

    # Энергия
    "энерг": "energy",
    "актив": "energy",
    "динамич": "energy",

    # Харизма
    "харизм": "charisma",
    "магнит": "charisma",
    "звезда": "charisma",
    "притяг": "charisma",
}


def theme_for(archetype: str) -> dict:
    """
    Возвращает тему по архетипу.
    Ищет ключевые слова. Если не найдено — дефолт.
    """
    if not archetype:
        return THEMES["default"]

    text = archetype.lower()
    for keyword, theme_name in KEYWORDS_TO_THEME.items():
        if keyword in text:
            return THEMES[theme_name]

    return THEMES["default"]


def theme_name_for(archetype: str) -> str:
    """Возвращает имя темы (для отладки)."""
    if not archetype:
        return "default"
    text = archetype.lower()
    for keyword, theme_name in KEYWORDS_TO_THEME.items():
        if keyword in text:
            return theme_name
    return "default"