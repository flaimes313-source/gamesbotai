import os
from io import BytesIO
from typing import Any, Dict

from PIL import Image, ImageDraw, ImageFont

CARD_WIDTH = 900
CARD_HEIGHT = 1200
BG_COLOR = (18, 18, 24)
ACCENT = (255, 90, 120)
TEXT = (240, 240, 240)
SUBTEXT = (180, 180, 200)


def _load_font(size: int):
    """Пытаемся найти системный шрифт. На BotHost/Linux обычно DejaVu Sans."""
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "C:\\Windows\\Fonts\\arialbd.ttf",
        "C:\\Windows\\Fonts\\arial.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def generate_card(profile: Dict[str, Any], username: str | None = None) -> bytes:
    img = Image.new("RGB", (CARD_WIDTH, CARD_HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(img)

    # Заголовок
    font_header = _load_font(34)
    font_archetype = _load_font(56)
    font_score = _load_font(38)
    font_small = _load_font(28)
    font_trait = _load_font(30)

    draw.text((60, 60), "AI SOCIAL GAME", font=font_header, fill=SUBTEXT)

    # Архетип
    archetype = str(profile.get("archetype", "")).upper()
    draw.text((60, 160), archetype, font=font_archetype, fill=ACCENT)

    # Скоры
    y = 320
    scores = profile.get("scores", {})
    label_map = {
        "charisma": "Харизма",
        "humor": "Юмор",
        "chaos": "Хаос",
        "energy": "Энергия",
        "intellect": "Интеллект",
        "creativity": "Креатив",
    }
    for key, label in label_map.items():
        value = int(scores.get(key, profile.get(key, 0)))
        draw.text((60, y), f"{label}", font=font_score, fill=TEXT)
        draw.text((600, y), f"{value}", font=font_score, fill=ACCENT)
        y += 70

    # Опасность
    y += 20
    danger = int(profile.get("danger_level", 0))
    draw.text((60, y), f"⚠️ Опасность для друзей: {danger}", font=font_small, fill=SUBTEXT)

    # Короткое описание
    y += 90
    description = str(profile.get("short_description") or profile.get("vibe") or "")[:120]
    _draw_wrapped(draw, description, font_trait, TEXT, 60, y, CARD_WIDTH - 120, line_height=44)

    # Username
    if username:
        draw.text((60, CARD_HEIGHT - 100), f"@{username}", font=font_small, fill=SUBTEXT)

    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _draw_wrapped(draw, text, font, fill, x, y, max_width, line_height=40):
    words = text.split()
    line = ""
    for word in words:
        test = f"{line} {word}".strip()
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] <= max_width:
            line = test
        else:
            draw.text((x, y), line, font=font, fill=fill)
            y += line_height
            line = word
    if line:
        draw.text((x, y), line, font=font, fill=fill)