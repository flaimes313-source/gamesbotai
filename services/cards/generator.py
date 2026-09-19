"""
Генератор карточек — неоновый дизайн «Вайбми».
Работает на встроенных в base64 шрифтах.
"""
import io
import logging
import random
from io import BytesIO
from typing import Any, Dict

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from services.cards.fonts_embedded import (
    get_bold_font_bytes,
    get_regular_font_bytes,
)
from services.cards.themes import theme_for, theme_name_for

_logger = logging.getLogger(__name__)

# Размеры карточки
CARD_W = 900
CARD_H = 1200


# ============================================================
# Загрузка шрифтов
# ============================================================
_FONT_REGULAR_BYTES = get_regular_font_bytes()
_FONT_BOLD_BYTES = get_bold_font_bytes()


def _load_font(size: int, bold: bool = False):
    data = _FONT_BOLD_BYTES if bold else _FONT_REGULAR_BYTES
    try:
        return ImageFont.truetype(io.BytesIO(data), size)
    except Exception as e:
        _logger.error(f"[CARDS] truetype failed (size={size}): {e}")
        return ImageFont.load_default()


# ============================================================
# Рисование градиента
# ============================================================
def _draw_gradient(img: Image.Image, top_color, bottom_color):
    """Вертикальный градиент сверху-вниз."""
    draw = ImageDraw.Draw(img)
    for y in range(CARD_H):
        t = y / max(1, CARD_H - 1)
        r = int(top_color[0] + (bottom_color[0] - top_color[0]) * t)
        g = int(top_color[1] + (bottom_color[1] - top_color[1]) * t)
        b = int(top_color[2] + (bottom_color[2] - top_color[2]) * t)
        draw.line([(0, y), (CARD_W, y)], fill=(r, g, b))


# ============================================================
# Свечения (glow)
# ============================================================
def _draw_glow_circle(img: Image.Image, center, radius: int, color, alpha: int = 40):
    """Размытое свечение — накладываем кружок через отдельный слой."""
    layer = Image.new("RGBA", (CARD_W, CARD_H), (0, 0, 0, 0))
    ldraw = ImageDraw.Draw(layer)
    ldraw.ellipse(
        [(center[0] - radius, center[1] - radius),
         (center[0] + radius, center[1] + radius)],
        fill=(color[0], color[1], color[2], alpha),
    )
    layer = layer.filter(ImageFilter.GaussianBlur(radius=80))
    img.alpha_composite(layer) if img.mode == "RGBA" else img.paste(
        layer, (0, 0), layer
    )


def _add_background_decorations(img: Image.Image, theme: dict):
    """Круги-разводы, сетка, боковая полоса."""
    accent = theme["accent"]
    accent2 = theme["accent2"]

    # Свечения в углах
    _draw_glow_circle(img, (150, 150), 250, accent, alpha=45)
    _draw_glow_circle(img, (CARD_W - 100, CARD_H - 250), 300, accent2, alpha=35)
    _draw_glow_circle(img, (CARD_W - 200, 400), 180, accent, alpha=25)

    # Тонкие горизонтальные линии
    draw = ImageDraw.Draw(img, "RGBA")
    for y in range(100, CARD_H, 120):
        draw.line([(0, y), (CARD_W, y)], fill=(255, 255, 255, 6), width=1)


def _add_side_stripe(img: Image.Image, theme: dict):
    """Вертикальная неоновая полоса слева."""
    draw = ImageDraw.Draw(img, "RGBA")
    accent = theme["accent"]
    draw.rectangle(
        [(0, 0), (4, CARD_H)],
        fill=(accent[0], accent[1], accent[2], 220),
    )


# ============================================================
# Отрисовка текста с обводкой
# ============================================================
def _draw_text_with_outline(draw, xy, text, font, fill, outline, width=2):
    x, y = xy
    for dx in range(-width, width + 1):
        for dy in range(-width, width + 1):
            if dx * dx + dy * dy <= width * width:
                draw.text((x + dx, y + dy), text, font=font, fill=outline)
    draw.text((x, y), text, font=font, fill=fill)


# ============================================================
# Основная функция
# ============================================================
def generate_card(
    profile: Dict[str, Any],
    username: str | None = None,
    bot_username: str | None = None,
) -> bytes:
    """
    Генерирует карточку «Вайбми» с неоновым дизайном.
    """
    archetype = str(profile.get("archetype", "ТВОЙ АРХЕТИП")).upper()
    theme = theme_for(archetype)
    theme_name = theme_name_for(archetype)
    _logger.info(f"[CARDS] theme={theme_name} for archetype='{archetype}'")

    # === Фон ===
    img = Image.new("RGB", (CARD_W, CARD_H), theme["bg_top"])
    _draw_gradient(img, theme["bg_top"], theme["bg_bottom"])
    img = img.convert("RGBA")
    _add_background_decorations(img, theme)
    _add_side_stripe(img, theme)

    draw = ImageDraw.Draw(img)

    # === Шапка ===
    font_header = _load_font(22, bold=False)
    font_hash = _load_font(22, bold=True)

    # Иконка архетипа — смайлик-«эмодзи» символами
    icon = _icon_for_theme(theme_name)

    draw.text((60, 55), icon, font=_load_font(40), fill=theme["accent"])
    draw.text((110, 65), "AI SOCIAL GAME", font=font_header, fill=theme["subtext"])

    # Хештег справа
    hashtag = f"#{theme_name}"
    bbox = draw.textbbox((0, 0), hashtag, font=font_hash)
    hashtag_w = bbox[2] - bbox[0]
    draw.text(
        (CARD_W - hashtag_w - 60, 65),
        hashtag,
        font=font_hash,
        fill=theme["accent"],
    )

    # Разделитель
    draw.rectangle(
        [(60, 120), (CARD_W - 60, 123)],
        fill=(theme["accent"][0], theme["accent"][1], theme["accent"][2], 200),
    )

    # === «МОЙ АРХЕТИП» ===
    font_label = _load_font(26, bold=False)
    label_text = "М О Й   А Р Х Е Т И П"
    bbox = draw.textbbox((0, 0), label_text, font=font_label)
    label_w = bbox[2] - bbox[0]
    draw.text(
        ((CARD_W - label_w) // 2, 180),
        label_text,
        font=font_label,
        fill=theme["subtext"],
    )

    # Декоративная линия над архетипом
    draw.line(
        [(CARD_W // 2 - 120, 230), (CARD_W // 2 + 120, 230)],
        fill=theme["accent"],
        width=2,
    )

    # === Архетип (плашка) ===
    font_archetype = _load_font(54, bold=True)
    bbox = draw.textbbox((0, 0), archetype, font=font_archetype)
    arch_w = bbox[2] - bbox[0]
    arch_h = bbox[3] - bbox[1]

    # Если слишком длинный — уменьшаем шрифт
    if arch_w > CARD_W - 200:
        font_archetype = _load_font(42, bold=True)
        bbox = draw.textbbox((0, 0), archetype, font=font_archetype)
        arch_w = bbox[2] - bbox[0]
        arch_h = bbox[3] - bbox[1]

    arch_x = (CARD_W - arch_w) // 2
    arch_y = 280

    # Плашка за архетипом
    padding_x, padding_y = 40, 25
    plate_box = [
        (arch_x - padding_x, arch_y - padding_y + 10),
        (arch_x + arch_w + padding_x, arch_y + arch_h + padding_y + 10),
    ]
    overlay = Image.new("RGBA", (CARD_W, CARD_H), (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)
    odraw.rounded_rectangle(
        plate_box,
        radius=22,
        fill=(theme["accent"][0], theme["accent"][1], theme["accent"][2], 45),
        outline=(theme["accent"][0], theme["accent"][1], theme["accent"][2], 220),
        width=3,
    )
    img.alpha_composite(overlay)

    # Текст архетипа
    draw.text(
        (arch_x, arch_y),
        archetype,
        font=font_archetype,
        fill=theme["text"],
    )

    # Декоративная линия под архетипом
    line_y = arch_y + arch_h + 60
    draw.line(
        [(CARD_W // 2 - 120, line_y), (CARD_W // 2 + 120, line_y)],
        fill=theme["accent"],
        width=2,
    )

    # === Скоры ===
    scores = profile.get("scores", {}) or {}
    score_rows = [
        ("charisma", "Харизма", "⚡"),
        ("humor", "Юмор", "😂"),
        ("chaos", "Хаос", "🧨"),
        ("intellect", "Интеллект", "🧠"),
        ("energy", "Энергия", "💥"),
        ("creativity", "Креатив", "🎨"),
    ]

    font_icon = _load_font(28)
    font_label_name = _load_font(28)
    font_score = _load_font(34, bold=True)

    y = 500
    bar_x = 400
    bar_w = 320
    bar_h = 22

    for key, label, icon in score_rows:
        value = int(scores.get(key, profile.get(key, 0)))
        value = max(0, min(100, value))

        # Иконка
        draw.text((60, y), icon, font=font_icon, fill=theme["text"])

        # Название
        draw.text((110, y + 2), label, font=font_label_name, fill=theme["text"])

        # Фон бара
        draw.rounded_rectangle(
            [(bar_x, y + 14), (bar_x + bar_w, y + 14 + bar_h)],
            radius=11,
            fill=(20, 20, 34, 255),
        )

        # Заливка бара — градиент (вручную, т.к. Pillow не умеет)
        fill_w = int(bar_w * value / 100)
        if fill_w > 0:
            # Рисуем заливку по частям для градиента
            for x in range(fill_w):
                t = x / max(1, fill_w - 1) if fill_w > 1 else 0
                r = int(theme["accent"][0] + (theme["accent2"][0] - theme["accent"][0]) * t)
                g = int(theme["accent"][1] + (theme["accent2"][1] - theme["accent"][1]) * t)
                b = int(theme["accent"][2] + (theme["accent2"][2] - theme["accent"][2]) * t)
                draw.line(
                    [(bar_x + x, y + 14), (bar_x + x, y + 14 + bar_h)],
                    fill=(r, g, b),
                )
            # Скругления поверх градиента
            draw.rounded_rectangle(
                [(bar_x, y + 14), (bar_x + fill_w, y + 14 + bar_h)],
                radius=11,
                outline=(r, g, b, 0),
            )

        # Число
        score_str = str(value)
        bbox = draw.textbbox((0, 0), score_str, font=font_score)
        score_w = bbox[2] - bbox[0]
        draw.text(
            (bar_x + bar_w + 30, y),
            score_str,
            font=font_score,
            fill=theme["accent"],
        )

        y += 65

    # === Опасность ===
    y += 20
    danger = int(profile.get("danger_level", 0))

    if danger >= 70:
        danger_color = (255, 51, 85)
        danger_icon = "🔥"
    elif danger >= 30:
        danger_color = (255, 190, 11)
        danger_icon = "⚠️"
    else:
        danger_color = (0, 200, 140)
        danger_icon = "💚"

    danger_text = f"{danger_icon}  ОПАСНОСТЬ ДЛЯ ДРУЗЕЙ"
    font_danger = _load_font(24, bold=True)

    # Плашка
    plate_x1, plate_y1 = 60, y
    plate_x2, plate_y2 = CARD_W - 60, y + 60

    overlay = Image.new("RGBA", (CARD_W, CARD_H), (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)
    odraw.rounded_rectangle(
        [(plate_x1, plate_y1), (plate_x2, plate_y2)],
        radius=14,
        fill=(danger_color[0], danger_color[1], danger_color[2], 30),
        outline=(danger_color[0], danger_color[1], danger_color[2], 200),
        width=2,
    )
    img.alpha_composite(overlay)

    draw.text((plate_x1 + 20, plate_y1 + 14), danger_text, font=font_danger, fill=danger_color)

    danger_num = f"{danger} / 100"
    bbox = draw.textbbox((0, 0), danger_num, font=font_danger)
    num_w = bbox[2] - bbox[0]
    draw.text(
        (plate_x2 - num_w - 20, plate_y1 + 14),
        danger_num,
        font=font_danger,
        fill=danger_color,
    )

    # === Цитата / вайб ===
    y += 100

    vibe = (
        profile.get("short_description")
        or profile.get("vibe")
        or "Уникальный вайб, который сложно описать словами."
    )
    vibe = str(vibe)[:200]

    font_quote = _load_font(26)

    # Плашка цитаты
    quote_pad = 25
    quote_lines = _wrap_text(draw, f"«{vibe}»", font_quote, CARD_W - 160)
    line_height = 40
    quote_h = len(quote_lines) * line_height + quote_pad * 2

    qx1, qy1 = 60, y
    qx2, qy2 = CARD_W - 60, y + quote_h + 30

    overlay = Image.new("RGBA", (CARD_W, CARD_H), (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)
    odraw.rounded_rectangle(
        [(qx1, qy1), (qx2, qy2)],
        radius=14,
        fill=(18, 18, 31, 255),
        outline=(theme["subtext"][0], theme["subtext"][1], theme["subtext"][2], 100),
        width=2,
    )
    img.alpha_composite(overlay)

    # Иконка 💬
    draw.text((qx1 + 20, qy1 + 15), "💬", font=_load_font(28), fill=theme["accent"])

    # Текст цитаты
    text_y = qy1 + quote_pad + 10
    for line in quote_lines:
        draw.text((qx1 + quote_pad + 40, text_y), line, font=font_quote, fill=theme["text"])
        text_y += line_height

    # === Достижения ===
    achievements = profile.get("achievements", [])
    if achievements:
        y = qy2 + 25
        achi_text = "   ·   ".join(achievements[:5])
        font_achi = _load_font(24)
        bbox = draw.textbbox((0, 0), achi_text, font=font_achi)
        aw = bbox[2] - bbox[0]
        draw.text(
            ((CARD_W - aw) // 2, y),
            achi_text,
            font=font_achi,
            fill=(255, 209, 102),
        )

    # === Футер ===
    footer_y = CARD_H - 80

    font_footer = _load_font(22)

    # Username слева
    if username:
        draw.text((60, footer_y), f"@{username}", font=font_footer, fill=theme["subtext"])

    # Bot username справа
    if bot_username:
        bot_str = f"@{bot_username}"
        bbox = draw.textbbox((0, 0), bot_str, font=font_footer)
        bw = bbox[2] - bbox[0]
        draw.text(
            (CARD_W - bw - 60, footer_y),
            bot_str,
            font=font_footer,
            fill=theme["subtext"],
        )

    # Слоган по центру
    slogan = "Вайбми · узнай свой вайб"
    font_slogan = _load_font(20, bold=True)
    bbox = draw.textbbox((0, 0), slogan, font=font_slogan)
    sw = bbox[2] - bbox[0]
    draw.text(
        ((CARD_W - sw) // 2, footer_y + 35),
        slogan,
        font=font_slogan,
        fill=theme["accent"],
    )

    # === Нижняя неоновая полоса ===
    draw.rectangle(
        [(0, CARD_H - 4), (CARD_W, CARD_H)],
        fill=(theme["accent"][0], theme["accent"][1], theme["accent"][2], 255),
    )

    # === Сохраняем ===
    buf = BytesIO()
    img.convert("RGB").save(buf, format="PNG", optimize=True)
    return buf.getvalue()


# ============================================================
# Утилиты
# ============================================================
def _wrap_text(draw, text: str, font, max_width: int) -> list:
    """Разбивает текст на строки по max_width."""
    words = text.split()
    lines = []
    current = ""
    for word in words:
        test = f"{current} {word}".strip()
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _icon_for_theme(theme_name: str) -> str:
    """Эмодзи-иконка в шапке под тему."""
    icons = {
        "chaos": "🧨",
        "calm": "🧊",
        "leader": "👑",
        "intellect": "🧠",
        "mystery": "🕵️",
        "humor": "😂",
        "creativity": "🎨",
        "danger": "🔥",
        "energy": "⚡",
        "charisma": "✨",
        "default": "✨",
    }
    return icons.get(theme_name, "✨")