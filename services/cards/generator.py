import logging
import os
from io import BytesIO
from typing import Any, Dict

from PIL import Image, ImageDraw, ImageFont

from services.cards.themes import theme_for

_logger = logging.getLogger(__name__)

CARD_WIDTH = 900
CARD_HEIGHT = 1200

# Пути к шрифтам в порядке приоритета.
# data/fonts — наши, лежат в репозитории, работают и локально, и на BotHost.
_FONT_DIRS = [
    "data/fonts",
    "/app/data/fonts",
    "/usr/share/fonts/truetype/dejavu",
    "/usr/share/fonts/dejavu",
    "/usr/share/fonts/TTF",
    "C:\\Windows\\Fonts",
]


def _find_font_file(bold: bool = False) -> str | None:
    """
    Ищет файл шрифта с кириллицей во всех известных директориях.
    Возвращает путь к первому найденному или None.
    """
    names = (
        ["DejaVuSans-Bold.ttf", "arialbd.ttf", "Arial Bold.ttf"]
        if bold
        else ["DejaVuSans.ttf", "arial.ttf", "Arial.ttf"]
    )

    for d in _FONT_DIRS:
        if not os.path.isdir(d):
            continue
        try:
            files = os.listdir(d)
        except Exception:
            continue
        for name in names:
            if name in files:
                return os.path.join(d, name)
    return None


_FONT_REGULAR = _find_font_file(bold=False)
_FONT_BOLD = _find_font_file(bold=True)


# ============================================================
# ДИАГНОСТИКА (можно убрать после отладки)
# ============================================================
_logger.info(f"[CARDS] cwd = {os.getcwd()}")
_logger.info(f"[CARDS] _FONT_REGULAR = {_FONT_REGULAR}")
_logger.info(f"[CARDS] _FONT_BOLD = {_FONT_BOLD}")
for _d in _FONT_DIRS:
    try:
        exists = os.path.isdir(_d)
        content = os.listdir(_d) if exists else None
        _logger.info(f"[CARDS] dir={_d} exists={exists} content={content}")
    except Exception as _e:
        _logger.error(f"[CARDS] dir={_d} error: {_e}")
# ============================================================


def _load_font(size: int, bold: bool = False):
    """
    Возвращает шрифт указанного размера.
    Если не нашли ни одного TTF — фолбэк на дефолтный (будут квадраты вместо кириллицы).
    """
    path = _FONT_BOLD if bold else _FONT_REGULAR
    if path:
        try:
            return ImageFont.truetype(path, size)
        except Exception as e:
            _logger.error(f"[CARDS] truetype({path}, {size}) failed: {e}")
    return ImageFont.load_default()


def _draw_wrapped(
    draw: ImageDraw.ImageDraw,
    text: str,
    font,
    fill,
    x: int,
    y: int,
    max_width: int,
    line_height: int = 40,
) -> int:
    """Рисует текст с переносом по словам. Возвращает итоговую Y-координату."""
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
        y += line_height
    return y


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

    # Боковая полоса
    draw.rectangle([(0, 0), (20, CARD_HEIGHT)], fill=theme["accent"])

    font_header = _load_font(28, bold=True)
    font_archetype = _load_font(52, bold=True)
    font_label = _load_font(30)
    font_score = _load_font(34, bold=True)
    font_small = _load_font(24)
    font_trait = _load_font(28)
    font_watermark = _load_font(22, bold=True)

    # ---------- Заголовок ----------
    draw.text((60, 55), "AI SOCIAL GAME", font=font_header, fill=theme["subtext"])

    # Разделитель
    draw.rectangle([(60, 100), (CARD_WIDTH - 60, 104)], fill=theme["accent"])

    # ---------- Архетип ----------
    y = 140
    y = _draw_wrapped(
        draw,
        archetype,
        font_archetype,
        theme["accent"],
        60,
        y,
        CARD_WIDTH - 120,
        line_height=65,
    )

    # ---------- Скоры ----------
    scores = profile.get("scores", {}) or {}
    label_map = [
        ("charisma", "Харизма"),
        ("humor", "Юмор"),
        ("chaos", "Хаос"),
        ("energy", "Энергия"),
        ("intellect", "Интеллект"),
        ("creativity", "Креатив"),
    ]

    y += 30
    for key, label in label_map:
        value = int(scores.get(key, profile.get(key, 0)))
        value = max(0, min(100, value))

        draw.text((60, y), label, font=font_label, fill=theme["text"])

        bar_x = 380
        bar_w = 380
        bar_h = 22
        draw.rectangle(
            [(bar_x, y + 12), (bar_x + bar_w, y + 12 + bar_h)],
            fill=theme["bg"],
            outline=theme["accent"],
            width=2,
        )
        filled_w = int(bar_w * value / 100)
        if filled_w > 0:
            draw.rectangle(
                [(bar_x, y + 12), (bar_x + filled_w, y + 12 + bar_h)],
                fill=theme["accent"],
            )
        draw.text(
            (bar_x + bar_w + 20, y),
            str(value),
            font=font_score,
            fill=theme["accent"],
        )
        y += 65

    # ---------- Опасность ----------
    y += 15
    danger = int(profile.get("danger_level", 0))
    draw.text(
        (60, y),
        f"Опасность для друзей: {danger}",
        font=font_small,
        fill=theme["subtext"],
    )

    # ---------- Описание ----------
    y += 70
    description = str(profile.get("short_description") or profile.get("vibe") or "")[:200]
    y = _draw_wrapped(
        draw,
        description,
        font_trait,
        theme["text"],
        60,
        y,
        CARD_WIDTH - 120,
        line_height=40,
    )

    # ---------- Нижняя полоса ----------
    draw.rectangle(
        [(0, CARD_HEIGHT - 70), (CARD_WIDTH, CARD_HEIGHT)],
        fill=theme["accent"],
    )

    if username:
        draw.text(
            (60, CARD_HEIGHT - 50),
            f"@{username}",
            font=font_watermark,
            fill=theme["bg"],
        )

    watermark = f"@{bot_username}" if bot_username else "AI SOCIAL GAME"
    bbox = draw.textbbox((0, 0), watermark, font=font_watermark)
    w = bbox[2] - bbox[0]
    draw.text(
        (CARD_WIDTH - w - 60, CARD_HEIGHT - 50),
        watermark,
        font=font_watermark,
        fill=theme["bg"],
    )

    buf = BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()