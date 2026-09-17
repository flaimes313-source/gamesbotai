import os
from io import BytesIO
from typing import Any, Dict

from PIL import Image, ImageDraw, ImageFont

from services.cards.themes import theme_for

CARD_WIDTH = 900
CARD_HEIGHT = 1200


def _load_font(size: int, bold: bool = False):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "C:\\Windows\\Fonts\\arialbd.ttf" if bold else "C:\\Windows\\Fonts\\arial.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _draw_wrapped(draw, text, font, fill, x, y, max_width, line_height=40):
    words = str(text).split()
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


def generate_card(
    profile: Dict[str, Any],
    username: str | None = None,
    bot_username: str | None = None,
) -> bytes:
    """
    Генерирует карточку результата с цветовой темой под архетип
    и водяным знаком @bot_username.
    """
    archetype = str(profile.get("archetype", "")).upper()
    theme = theme_for(archetype)

    img = Image.new("RGB", (CARD_WIDTH, CARD_HEIGHT), theme["bg"])
    draw = ImageDraw.Draw(img)

    # боковая полоса
    draw.rectangle([(0, 0), (20, CARD_HEIGHT)], fill=theme["accent"])

    font_header = _load_font(30, bold=True)
    font_archetype = _load_font(58, bold=True)
    font_score = _load_font(38, bold=True)
    font_label = _load_font(34)
    font_small = _load_font(26)
    font_trait = _load_font(30)
    font_watermark = _load_font(24, bold=True)

    # Заголовок
    draw.text((60, 60), "AI SOCIAL GAME", font=font_header, fill=theme["subtext"])

    # Разделительная линия
    draw.rectangle([(60, 110), (CARD_WIDTH - 60, 114)], fill=theme["accent"])

    # Архетип (может быть длинным — переносим)
    _draw_wrapped(draw, archetype, font_archetype, theme["accent"], 60, 150, CARD_WIDTH - 120, line_height=70)

    # Скоры
    scores = profile.get("scores", {}) or {}
    label_map = [
        ("charisma", "Харизма"),
        ("humor", "Юмор"),
        ("chaos", "Хаос"),
        ("energy", "Энергия"),
        ("intellect", "Интеллект"),
        ("creativity", "Креатив"),
    ]

    y = 400
    for key, label in label_map:
        value = int(scores.get(key, profile.get(key, 0)))
        draw.text((60, y), label, font=font_label, fill=theme["text"])
        # полоска прогресса
        bar_x = 380
        bar_w = 380
        bar_h = 22
        draw.rectangle([(bar_x, y + 12), (bar_x + bar_w, y + 12 + bar_h)], fill=theme["bg"])
        draw.rectangle([(bar_x, y + 12), (bar_x + int(bar_w * value / 100), y + 12 + bar_h)], fill=theme["accent"])
        draw.text((bar_x + bar_w + 20, y), str(value), font=font_score, fill=theme["accent"])
        y += 70

    # Опасность
    y += 20
    danger = int(profile.get("danger_level", 0))
    draw.text((60, y), f"⚠️ Опасность для друзей: {danger}", font=font_small, fill=theme["subtext"])

    # Короткое описание
    y += 80
    description = str(profile.get("short_description") or profile.get("vibe") or "")[:180]
    _draw_wrapped(draw, description, font_trait, theme["text"], 60, y, CARD_WIDTH - 120, line_height=42)

    # Нижняя полоса с водяным знаком
    draw.rectangle([(0, CARD_HEIGHT - 70), (CARD_WIDTH, CARD_HEIGHT)], fill=theme["accent"])
    watermark = f"@{bot_username}" if bot_username else "AI SOCIAL GAME"
    if username:
        left_text = f"@{username}"
        draw.text((60, CARD_HEIGHT - 55), left_text, font=font_watermark, fill=theme["bg"])
    bbox = draw.textbbox((0, 0), watermark, font=font_watermark)
    w = bbox[2] - bbox[0]
    draw.text((CARD_WIDTH - w - 60, CARD_HEIGHT - 55), watermark, font=font_watermark, fill=theme["bg"])

    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()