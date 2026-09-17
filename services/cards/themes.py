from typing import Dict

# Палитры (background, accent, text, subtext)
THEMES: Dict[str, dict] = {
    "chaos": {
        "bg": (24, 12, 32),
        "accent": (255, 90, 120),
        "text": (245, 235, 240),
        "subtext": (200, 170, 200),
    },
    "calm": {
        "bg": (16, 24, 32),
        "accent": (100, 200, 220),
        "text": (235, 245, 250),
        "subtext": (170, 195, 210),
    },
    "leader": {
        "bg": (30, 22, 12),
        "accent": (255, 190, 70),
        "text": (250, 240, 220),
        "subtext": (210, 190, 150),
    },
    "intellect": {
        "bg": (12, 22, 18),
        "accent": (100, 220, 140),
        "text": (235, 250, 240),
        "subtext": (170, 210, 185),
    },
    "default": {
        "bg": (18, 18, 24),
        "accent": (255, 90, 120),
        "text": (240, 240, 240),
        "subtext": (180, 180, 200),
    },
}

# Ключевые слова → тема
KEYWORDS = {
    "хаос": "chaos",
    "chaos": "chaos",
    "манипулятор": "calm",
    "спокойный": "calm",
    "лидер": "leader",
    "главный": "leader",
    "интеллект": "intellect",
    "мозг": "intellect",
    "идеи": "intellect",
}


def theme_for(archetype: str) -> dict:
    text = (archetype or "").lower()
    for kw, theme in KEYWORDS.items():
        if kw in text:
            return THEMES[theme]
    return THEMES["default"]