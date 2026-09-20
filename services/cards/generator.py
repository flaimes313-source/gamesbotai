"""
Генератор карточек «Вайбми».
Без эмодзи (используем геометрические маркеры).
"""
import io
import logging
from io import BytesIO
from typing import Any, Dict

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from services.cards.fonts_embedded import (
    get_bold_font_bytes,
    get_regular_font_bytes,
)
from services.cards.themes import tag_for_archetype, theme_for, theme_name_for

_logger = logging.getLogger(__name__)

CARD_W = 900
CARD_H = 1200


# ============================================================
# Шрифты
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
# Утилиты рисования
# ============================================================
def _draw_gradient(img: Image.Image, top_color, bottom_color):
    draw = ImageDraw.Draw(img)
    for y in range(CARD_H):
        t = y / max(1, CARD_H - 1)
        r = int(top_color[0] + (bottom_color[0] - top_color[0]) * t)
        g = int(top_color[1] + (bottom_color[1] - top_color[1]) * t)
        b = int(top_color[2] + (bottom_color[2] - top_color[2]) * t)
        draw.line([(0, y), (CARD_W, y)], fill=(r, g, b))


def _draw_glow_circle(img: Image.Image, center, radius: int, color, alpha: int = 40):
    layer = Image.new("RGBA", (CARD_W, CARD_H), (0, 0, 0, 0))
    ldraw = ImageDraw.Draw(layer)
    ldraw.ellipse(
        [(center[0] - radius, center[1] - radius),
         (center[0] + radius, center[1] + radius)],
        fill=(color[0], color[1], color[2], alpha),
    )
    layer = layer.filter(ImageFilter.GaussianBlur(radius=80))
    img.alpha_composite(layer)


def _wrap_text(draw, text: str, font, max_width: int) -> list:
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


def _text_width(draw, text, font):
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0]


# ============================================================
# Основная функция
# ============================================================
def generate_card(
    profile: Dict[str, Any],
    username: str | None = None,
    bot_username: str | None = None,
) -> bytes:
    """
    Генерирует карточку «Вайбми».
    """
    archetype = str(profile.get("archetype", "ТВОЙ АРХЕТИП")).upper()
    theme = theme_for(archetype)
    theme_name = theme_name_for(archetype)
    hashtag = tag_for_archetype(archetype)
    _logger.info(f"[CARDS] theme={theme_name} archetype='{archetype}' tag={hashtag}")

    # === Фон ===
    img = Image.new("RGB", (CARD_W, CARD_H), theme["bg_top"])
    _draw_gradient(img, theme["bg_top"], theme["bg_bottom"])
    img = img.convert("RGBA")

    # Свечения
    _draw_glow_circle(img, (150, 150), 250, theme["accent"], alpha=40)
    _draw_glow_circle(img, (CARD_W - 100, CARD_H - 300), 280, theme["accent2"], alpha=30)
    _draw_glow_circle(img, (CARD_W - 200, 400), 150, theme["accent"], alpha=20)

    draw = ImageDraw.Draw(img)

    # Боковая полоса
    draw.rectangle(
        [(0, 0), (4, CARD_H)],
        fill=(theme["accent"][0], theme["accent"][1], theme["accent"][2], 220),
    )

    # ============================================================
    # ШАПКА: ВАЙБМИ + тег
    # ============================================================
    font_brand = _load_font(24, bold=True)
    font_tag = _load_font(20, bold=True)

    draw.text((60, 55), "ВАЙБМИ", font=font_brand, fill=theme["accent"])
    # Подпись под брендом
    font_sub = _load_font(14)
    draw.text((60, 85), "узнай свой вайб", font=font_sub, fill=theme["subtext"])

    # Тег справа
    tag_w = _text_width(draw, hashtag, font_tag)
    draw.text(
        (CARD_W - tag_w - 60, 60),
        hashtag,
        font=font_tag,
        fill=theme["accent"],
    )

    # ============================================================
    # БЛОК: МОЙ АРХЕТИП
    # ============================================================
    font_label = _load_font(22, bold=False)
    label_text = "М О Й   А Р Х Е Т И П"
    label_w = _text_width(draw, label_text, font_label)
    draw.text(
        ((CARD_W - label_w) // 2, 180),
        label_text,
        font=font_label,
        fill=theme["subtext"],
    )

    # Архетип
    font_archetype = _load_font(52, bold=True)
    # Уменьшаем если не влезает
    if _text_width(draw, archetype, font_archetype) > CARD_W - 200:
        font_archetype = _load_font(38, bold=True)
    if _text_width(draw, archetype, font_archetype) > CARD_W - 200:
        font_archetype = _load_font(30, bold=True)

    arch_w = _text_width(draw, archetype, font_archetype)
    arch_x = (CARD_W - arch_w) // 2
    arch_y = 240

    # Плашка
    bbox = draw.textbbox((0, 0), archetype, font=font_archetype)
    arch_h = bbox[3] - bbox[1]

    padding_x, padding_y = 40, 28
    plate_box = [
        (arch_x - padding_x, arch_y - padding_y + 10),
        (arch_x + arch_w + padding_x, arch_y + arch_h + padding_y + 10),
    ]

    overlay = Image.new("RGBA", (CARD_W, CARD_H), (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)
    odraw.rounded_rectangle(
        plate_box,
        radius=22,
        fill=(theme["accent"][0], theme["accent"][1], theme["accent"][2], 40),
        outline=(theme["accent"][0], theme["accent"][1], theme["accent"][2], 220),
        width=3,
    )
    img.alpha_composite(overlay)

    draw.text((arch_x, arch_y), archetype, font=font_archetype, fill=theme["text"])

    # ============================================================
    # БЛОК: ХАРАКТЕРИСТИКИ
    # ============================================================
    scores = profile.get("scores", {}) or {}
    score_rows = [
        ("charisma", "Харизма"),
        ("humor", "Юмор"),
        ("chaos", "Хаос"),
        ("intellect", "Интеллект"),
        ("energy", "Энергия"),
        ("creativity", "Креатив"),
    ]

    font_label_name = _load_font(26)
    font_score = _load_font(32, bold=True)

    y = 460
    bar_x = 420
    bar_w = 300
    bar_h = 18
    row_step = 62

    for key, label in score_rows:
        value = int(scores.get(key, profile.get(key, 0)))
        value = max(0, min(100, value))

        # Маркер (маленький ромб)
        marker_x = 60
        marker_y = y + 12
        draw.polygon(
            [
                (marker_x + 8, marker_y),
                (marker_x + 16, marker_y + 8),
                (marker_x + 8, marker_y + 16),
                (marker_x, marker_y + 8),
            ],
            fill=theme["accent"],
        )

        # Название
        draw.text((90, y + 2), label, font=font_label_name, fill=theme["text"])

        # Фон бара
        draw.rounded_rectangle(
            [(bar_x, y + 13), (bar_x + bar_w, y + 13 + bar_h)],
            radius=9,
            fill=(20, 20, 34, 255),
        )

        # Заливка с градиентом
        fill_w = int(bar_w * value / 100)
        if fill_w > 0:
            for x in range(fill_w):
                t = x / max(1, fill_w - 1) if fill_w > 1 else 0
                r = int(theme["accent"][0] + (theme["accent2"][0] - theme["accent"][0]) * t)
                g = int(theme["accent"][1] + (theme["accent2"][1] - theme["accent"][1]) * t)
                b = int(theme["accent"][2] + (theme["accent2"][2] - theme["accent"][2]) * t)
                draw.line(
                    [(bar_x + x, y + 13), (bar_x + x, y + 13 + bar_h)],
                    fill=(r, g, b),
                )

        # Число
        score_str = str(value)
        draw.text(
            (bar_x + bar_w + 25, y),
            score_str,
            font=font_score,
            fill=theme["accent"],
        )

        y += row_step

    # ============================================================
    # ОПАСНОСТЬ
    # ============================================================
    y += 10
    danger = int(profile.get("danger_level", 0))

    if danger >= 70:
        danger_color = (255, 51, 85)
    elif danger >= 30:
        danger_color = (255, 190, 11)
    else:
        danger_color = (0, 200, 140)

    font_danger = _load_font(22, bold=True)
    danger_text = "ОПАСНОСТЬ ДЛЯ ДРУЗЕЙ"

    plate_x1, plate_y1 = 60, y
    plate_x2, plate_y2 = CARD_W - 60, y + 55

    overlay = Image.new("RGBA", (CARD_W, CARD_H), (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)
    odraw.rounded_rectangle(
        [(plate_x1, plate_y1), (plate_x2, plate_y2)],
        radius=14,
        fill=(danger_color[0], danger_color[1], danger_color[2], 25),
        outline=(danger_color[0], danger_color[1], danger_color[2], 180),
        width=2,
    )
    img.alpha_composite(overlay)

    draw.text((plate_x1 + 25, plate_y1 + 16), danger_text, font=font_danger, fill=danger_color)

    danger_num = f"{danger} / 100"
    num_w = _text_width(draw, danger_num, font_danger)
    draw.text(
        (plate_x2 - num_w - 25, plate_y1 + 16),
        danger_num,
        font=font_danger,
        fill=danger_color,
    )

    # ============================================================
    # ЦИТАТА / ВАЙБ
    # ============================================================
    y = plate_y2 + 25

    vibe = (
        profile.get("short_description")
        or profile.get("vibe")
        or "Уникальный вайб, который сложно описать словами."
    )
    vibe = str(vibe)[:200]

    font_quote = _load_font(24)

    quote_pad = 22
    quote_lines = _wrap_text(draw, f"«{vibe}»", font_quote, CARD_W - 160)
    line_height = 36
    quote_h = len(quote_lines) * line_height + quote_pad * 2 + 10

    qx1, qy1 = 60, y
    qx2, qy2 = CARD_W - 60, y + quote_h

    overlay = Image.new("RGBA", (CARD_W, CARD_H), (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)
    odraw.rounded_rectangle(
        [(qx1, qy1), (qx2, qy2)],
        radius=16,
        fill=(18, 18, 31, 240),
        outline=(theme["accent"][0], theme["accent"][1], theme["accent"][2], 90),
        width=2,
    )
    img.alpha_composite(overlay)

    # Полоска слева цитаты
    draw.rectangle(
        [(qx1 + 3, qy1 + 15), (qx1 + 5, qy2 - 15)],
        fill=theme["accent"],
    )

    # Текст цитаты
    text_y = qy1 + quote_pad + 5
    for line in quote_lines:
        draw.text((qx1 + quote_pad + 20, text_y), line, font=font_quote, fill=theme["text"])
        text_y += line_height

    # ============================================================
    # ДОСТИЖЕНИЯ
    # ============================================================
    achievements = profile.get("achievements", [])
    if achievements:
        achi_y = qy2 + 20
        achi_text = "   ·   ".join(achievements[:5])
        font_achi = _load_font(20)
        aw = _text_width(draw, achi_text, font_achi)
        draw.text(
            ((CARD_W - aw) // 2, achi_y),
            achi_text,
            font=font_achi,
            fill=(255, 209, 102),
        )

    # ============================================================
    # ФУТЕР (без username!)
    # ============================================================
    footer_y = CARD_H - 70

    # Слоган слева
    slogan = "ВАЙБМИ"
    font_slogan = _load_font(20, bold=True)
    draw.text((60, footer_y), slogan, font=font_slogan, fill=theme["accent"])

    slogan_sub = "узнай свой вайб"
    font_slogan_sub = _load_font(13)
    draw.text((60, footer_y + 28), slogan_sub, font=font_slogan_sub, fill=theme["subtext"])

    # Bot username справа
    if bot_username:
        bot_str = f"@{bot_username}"
        font_bot = _load_font(18)
        bw = _text_width(draw, bot_str, font_bot)
        draw.text(
            (CARD_W - bw - 60, footer_y + 8),
            bot_str,
            font=font_bot,
            fill=theme["subtext"],
        )

    # Нижняя полоса
    draw.rectangle(
        [(0, CARD_H - 4), (CARD_W, CARD_H)],
        fill=(theme["accent"][0], theme["accent"][1], theme["accent"][2], 255),
    )

    # === Сохраняем ===
    buf = BytesIO()
    img.convert("RGB").save(buf, format="PNG", optimize=True)
    return buf.getvalue()