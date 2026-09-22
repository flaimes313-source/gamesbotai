"""
Генератор карточек «Вайбми».
Работает на Python 3.7+. Иконки вшиты в base64.

Правка: поддержка ЛЕГЕНДАРНЫХ архетипов.
- Параметр is_legendary: bool = False.
- При True — золотая рамка, золотые свечения,
  значок «ЛЕГЕНДАРНЫЙ» и особый заголовок.
- Тема 'legendary' подбирается автоматически через
  themes.theme_for(), т.к. архетип уже легендарный.
"""
import io
import logging
import math
from io import BytesIO
from typing import Any, Dict, Optional

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from services.cards.fonts_embedded import (
    get_bold_font_bytes,
    get_regular_font_bytes,
)
from services.cards.icons import achievement_icon, stat_icon
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


def _draw_star(draw, cx: int, cy: int, size: int, color, points: int = 5):
    """
    Рисует звёздочку (для значка «легендарный»).
    Без PNG, чистым Polygon — чтобы не плодить base64.
    """
    inner = size * 0.42
    coords = []
    for i in range(points * 2):
        angle = math.pi / 2 * 3 + i * math.pi / points
        r = size if i % 2 == 0 else inner
        x = cx + r * math.cos(angle)
        y = cy - r * math.sin(angle)
        coords.append((x, y))
    draw.polygon(coords, fill=color)


def _draw_legendary_border(img: Image.Image, accent, accent2, width: int = 10):
    """
    Рисует золотую рамку по периметру карточки.
    Внутренняя линия — accent2, внешняя — accent.
    Рисуется поверх всего в самом конце.
    """
    draw = ImageDraw.Draw(img)
    # Внешний контур
    draw.rectangle(
        [(0, 0), (CARD_W - 1, CARD_H - 1)],
        outline=(accent[0], accent[1], accent[2], 255),
        width=width,
    )
    # Внутренняя тонкая линия для «двойной» рамки
    inset = width + 4
    draw.rectangle(
        [(inset, inset), (CARD_W - 1 - inset, CARD_H - 1 - inset)],
        outline=(accent2[0], accent2[1], accent2[2], 180),
        width=2,
    )


def _draw_legendary_badge(img: Image.Image, theme, top: int = 130, right_pad: int = 60):
    """
    Рисует плашку «✨ ЛЕГЕНДАРНЫЙ» в правом верхнем углу.
    top — вертикальная позиция под хэштегом.
    """
    draw = ImageDraw.Draw(img)

    font_badge = _load_font(18, bold=True)
    badge_text = "ЛЕГЕНДАРНЫЙ"

    text_w = _text_width(draw, badge_text, font_badge)
    bbox = draw.textbbox((0, 0), badge_text, font=font_badge)
    text_h = bbox[3] - bbox[1]

    star_size = 12
    star_gap = 10
    pad_x = 18
    pad_y = 10

    badge_w = pad_x * 2 + star_size * 2 + star_gap * 2 + text_w
    badge_h = pad_y * 2 + max(text_h, star_size * 2)

    x2 = CARD_W - right_pad
    x1 = x2 - badge_w
    y1 = top
    y2 = y1 + badge_h

    # Плашка
    overlay = Image.new("RGBA", (CARD_W, CARD_H), (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)
    odraw.rounded_rectangle(
        [(x1, y1), (x2, y2)],
        radius=14,
        fill=(theme["accent"][0], theme["accent"][1], theme["accent"][2], 55),
        outline=(theme["accent"][0], theme["accent"][1], theme["accent"][2], 240),
        width=2,
    )
    img.alpha_composite(overlay)

    # Звёздочки
    star_cy = (y1 + y2) // 2
    star1_cx = x1 + pad_x + star_size
    star2_cx = x1 + pad_x + star_size * 2 + star_gap + star_size
    _draw_star(draw, star1_cx, star_cy, star_size, theme["accent"])
    _draw_star(draw, star2_cx, star_cy, star_size, theme["accent2"])

    # Текст
    text_x = x1 + pad_x + star_size * 2 + star_gap * 2
    text_y = y1 + pad_y
    draw.text((text_x, text_y), badge_text, font=font_badge, fill=theme["accent"])


# ============================================================
# Основная функция
# ============================================================
def generate_card(
    profile: Dict[str, Any],
    username: Optional[str] = None,
    bot_username: Optional[str] = None,
    is_legendary: bool = False,
) -> bytes:
    archetype = str(profile.get("archetype", "ТВОЙ АРХЕТИП")).upper()
    theme = theme_for(archetype)
    theme_name = theme_name_for(archetype)
    hashtag = tag_for_archetype(archetype)

    # Если передан is_legendary=True, но тема не legendary
    # (например, архетип не входит в список — защита) —
    # принудительно берём legendary тему.
    if is_legendary and theme_name != "legendary":
        from services.cards.themes import THEMES
        theme = THEMES["legendary"]
        theme_name = "legendary"

    _logger.info(
        f"[CARDS] theme={theme_name} archetype='{archetype}' "
        f"tag={hashtag} legendary={is_legendary}"
    )

    # === Фон ===
    img = Image.new("RGB", (CARD_W, CARD_H), theme["bg_top"])
    _draw_gradient(img, theme["bg_top"], theme["bg_bottom"])
    img = img.convert("RGBA")

    # Свечения: при легендарке — усиленные золотые
    if is_legendary:
        _draw_glow_circle(img, (150, 150), 300, theme["accent"], alpha=65)
        _draw_glow_circle(img, (CARD_W - 100, CARD_H - 300), 320, theme["accent2"], alpha=50)
        _draw_glow_circle(img, (CARD_W - 200, 400), 200, theme["accent"], alpha=40)
        _draw_glow_circle(img, (200, CARD_H - 200), 220, theme["accent2"], alpha=35)
    else:
        _draw_glow_circle(img, (150, 150), 250, theme["accent"], alpha=40)
        _draw_glow_circle(img, (CARD_W - 100, CARD_H - 300), 280, theme["accent2"], alpha=30)
        _draw_glow_circle(img, (CARD_W - 200, 400), 150, theme["accent"], alpha=20)

    draw = ImageDraw.Draw(img)

    # Боковая полоса (при легендарке — шире и золотая)
    side_w = 8 if is_legendary else 4
    draw.rectangle(
        [(0, 0), (side_w, CARD_H)],
        fill=(theme["accent"][0], theme["accent"][1], theme["accent"][2], 230),
    )

    # === ШАПКА ===
    font_brand = _load_font(24, bold=True)
    font_tag = _load_font(20, bold=True)
    font_sub = _load_font(14)

    draw.text((60, 55), "ВАЙБМИ", font=font_brand, fill=theme["accent"])
    draw.text((60, 85), "узнай свой вайб", font=font_sub, fill=theme["subtext"])

    tag_w = _text_width(draw, hashtag, font_tag)
    draw.text(
        (CARD_W - tag_w - 60, 60),
        hashtag,
        font=font_tag,
        fill=theme["accent"],
    )

    # Значок «ЛЕГЕНДАРНЫЙ» — под хэштегом
    if is_legendary:
        _draw_legendary_badge(img, theme, top=100, right_pad=60)

    # === МОЙ АРХЕТИП (или ЛЕГЕНДАРНЫЙ АРХЕТИП) ===
    font_label = _load_font(22, bold=False)
    if is_legendary:
        label_text = "Л Е Г Е Н Д А Р Н Ы Й   А Р Х Е Т И П"
    else:
        label_text = "М О Й   А Р Х Е Т И П"

    label_w = _text_width(draw, label_text, font_label)
    label_y = 200 if is_legendary else 180
    draw.text(
        ((CARD_W - label_w) // 2, label_y),
        label_text,
        font=font_label,
        fill=theme["subtext"],
    )

    font_archetype = _load_font(52, bold=True)
    if _text_width(draw, archetype, font_archetype) > CARD_W - 200:
        font_archetype = _load_font(38, bold=True)
    if _text_width(draw, archetype, font_archetype) > CARD_W - 200:
        font_archetype = _load_font(30, bold=True)

    arch_w = _text_width(draw, archetype, font_archetype)
    arch_x = (CARD_W - arch_w) // 2
    arch_y = 260 if is_legendary else 240

    bbox = draw.textbbox((0, 0), archetype, font=font_archetype)
    arch_h = bbox[3] - bbox[1]

    padding_x, padding_y = 40, 28
    plate_box = [
        (arch_x - padding_x, arch_y - padding_y + 10),
        (arch_x + arch_w + padding_x, arch_y + arch_h + padding_y + 10),
    ]

    # Двойная обводка плашки архетипа при легендарке
    if is_legendary:
        overlay = Image.new("RGBA", (CARD_W, CARD_H), (0, 0, 0, 0))
        odraw = ImageDraw.Draw(overlay)
        # Внешняя золотая
        odraw.rounded_rectangle(
            plate_box,
            radius=24,
            fill=(theme["accent"][0], theme["accent"][1], theme["accent"][2], 55),
            outline=(theme["accent"][0], theme["accent"][1], theme["accent"][2], 255),
            width=4,
        )
        # Внутренняя тонкая
        inner_box = [
            (plate_box[0][0] + 8, plate_box[0][1] + 8),
            (plate_box[1][0] - 8, plate_box[1][1] - 8),
        ]
        odraw.rounded_rectangle(
            inner_box,
            radius=18,
            outline=(theme["accent2"][0], theme["accent2"][1], theme["accent2"][2], 200),
            width=2,
        )
        img.alpha_composite(overlay)
    else:
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
    # ХАРАКТЕРИСТИКИ — с PNG-иконками
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

    # Сдвигаем блок характеристик вниз, если легендарка (там больше шапка)
    y = 480 if is_legendary else 460
    icon_size = 40
    text_x = 60 + icon_size + 15
    bar_x = 420
    bar_w = 300
    bar_h = 18
    row_step = 62

    for key, label in score_rows:
        value = int(scores.get(key, profile.get(key, 0)))
        value = max(0, min(100, value))

        # Иконка PNG
        icon = stat_icon(key, size=icon_size)
        if icon is not None:
            img.alpha_composite(icon, (60, y + 4))
        else:
            # Фолбэк — ромб
            draw.polygon(
                [
                    (60 + 16, y + 6),
                    (60 + 32, y + 22),
                    (60 + 16, y + 38),
                    (60, y + 22),
                ],
                fill=theme["accent"],
            )

        # Название
        draw.text((text_x, y + 10), label, font=font_label_name, fill=theme["text"])

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
        draw.text(
            (bar_x + bar_w + 25, y + 8),
            str(value),
            font=font_score,
            fill=theme["accent"],
        )

        y += row_step

    # === ОПАСНОСТЬ ===
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

    # === ЦИТАТА ===
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

    draw.rectangle(
        [(qx1 + 3, qy1 + 15), (qx1 + 5, qy2 - 15)],
        fill=theme["accent"],
    )

    text_y = qy1 + quote_pad + 5
    for line in quote_lines:
        draw.text((qx1 + quote_pad + 20, text_y), line, font=font_quote, fill=theme["text"])
        text_y += line_height

    # ============================================================
    # ДОСТИЖЕНИЯ — с PNG-иконками
    # ============================================================
    achievements = profile.get("achievements", [])
    if achievements:
        achi_y = qy2 + 25

        icons_with_size = 32
        gap = 22
        total_w = 0
        pairs = []
        for code in achievements[:5]:
            icon = achievement_icon(code, size=icons_with_size)
            if icon is None:
                continue
            pairs.append((code, icon))
            total_w += icons_with_size + gap

        if pairs:
            total_w -= gap
            start_x = (CARD_W - total_w) // 2

            for code, icon in pairs:
                img.alpha_composite(icon, (start_x, achi_y))
                start_x += icons_with_size + gap

    # === ФУТЕР ===
    footer_y = CARD_H - 70

    font_slogan = _load_font(20, bold=True)
    draw.text((60, footer_y), "ВАЙБМИ", font=font_slogan, fill=theme["accent"])

    font_slogan_sub = _load_font(13)
    draw.text((60, footer_y + 28), "узнай свой вайб", font=font_slogan_sub, fill=theme["subtext"])

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

    draw.rectangle(
        [(0, CARD_H - 4), (CARD_W, CARD_H)],
        fill=(theme["accent"][0], theme["accent"][1], theme["accent"][2], 255),
    )

    # === ЛЕГЕНДАРНАЯ РАМКА — поверх всего ===
    if is_legendary:
        _draw_legendary_border(img, theme["accent"], theme["accent2"], width=10)

    buf = BytesIO()
    img.convert("RGB").save(buf, format="PNG", optimize=True)
    return buf.getvalue()