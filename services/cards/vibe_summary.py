"""
Карточка «Твой вайб-месяц» (Шаг 1.3.2).

Отдельный модуль — не трогает основной генератор карточек.
Рисует недельную/месячную сводку:
- заголовок «ТВОЙ ВАЙБ-МЕСЯЦ»,
- крупный summary от AI,
- 6 плиток с ключевыми цифрами,
- футер.

Размер 900×1200 — как основная карточка, для единообразия.
Тема берётся по последнему архетипу юзера. Если есть легендарка —
используется тема 'legendary' (золото).
"""
import io
import logging
from io import BytesIO
from typing import Any, Dict, Optional

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from services.cards.fonts_embedded import (
    get_bold_font_bytes,
    get_regular_font_bytes,
)
from services.cards.icons import stat_icon
from services.cards.themes import theme_for
from services.analysis.rarity import is_legendary

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
        _logger.error(f"[VIBE_CARD] truetype failed (size={size}): {e}")
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


def _text_width(draw, text, font):
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0]


def _wrap_text(draw, text: str, font, max_width: int) -> list:
    """Простой word-wrap по ширине."""
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


# ============================================================
# Плитки с цифрами
# ============================================================
def _draw_stat_tile(
    img: Image.Image,
    x: int, y: int,
    w: int, h: int,
    icon_key: str,
    label: str,
    value: str,
    theme: Dict[str, Any],
):
    """
    Рисует одну плитку: иконка + название + крупное число.
    Координаты x, y — верхний левый угол плитки.
    """
    draw = ImageDraw.Draw(img)
    accent = theme["accent"]
    accent2 = theme["accent2"]
    text_color = theme["text"]
    subtext = theme["subtext"]

    # Фон плитки (полупрозрачный)
    overlay = Image.new("RGBA", (CARD_W, CARD_H), (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)
    odraw.rounded_rectangle(
        [(x, y), (x + w, y + h)],
        radius=18,
        fill=(accent[0], accent[1], accent[2], 22),
        outline=(accent[0], accent[1], accent[2], 120),
        width=2,
    )
    img.alpha_composite(overlay)

    # Иконка (слева)
    icon_size = 42
    icon = stat_icon(icon_key, size=icon_size) if icon_key else None
    icon_x = x + 22
    icon_y = y + (h - icon_size) // 2
    if icon is not None:
        img.alpha_composite(icon, (icon_x, icon_y))
    else:
        # Фолбэк — ромб
        cx = icon_x + icon_size // 2
        cy = icon_y + icon_size // 2
        r = 16
        draw.polygon(
            [(cx, cy - r), (cx + r, cy), (cx, cy + r), (cx - r, cy)],
            fill=accent,
        )

    # Текст: название сверху, число снизу
    text_x = icon_x + icon_size + 18

    font_label = _load_font(18)
    font_value = _load_font(36, bold=True)

    # Название
    draw.text(
        (text_x, y + 20),
        label,
        font=font_label,
        fill=subtext,
    )
    # Значение
    draw.text(
        (text_x, y + 46),
        value,
        font=font_value,
        fill=text_color,
    )


# ============================================================
# Основная функция
# ============================================================
def generate_vibe_summary_card(
    summary: str,
    stats: Dict[str, Any],
    archetype: Optional[str] = None,
    bot_username: Optional[str] = None,
    period_label: Optional[str] = None,
) -> bytes:
    """
    Рисует карточку «Твой вайб-месяц».

    Параметры:
        summary — короткая фраза от AI (1 строка, без HTML).
        stats — словарь метрик:
            {
                "total_analyses": int,
                "total_points": int,
                "current_streak": int,
                "active_days": int,
                "unique_archetypes": int,
                "legendary_count": int,
            }
        archetype — текущий архетип (для выбора темы).
        bot_username — @username для футера.
        period_label — надпись под заголовком, напр. «Неделя: 15.09 — 21.09».

    Возвращает PNG-байты.
    """
    # --- Тема ---
    theme_archetype = archetype or "default"
    if archetype and is_legendary(archetype):
        theme_archetype = archetype  # theme_for уже вернёт legendary
    theme = theme_for(theme_archetype)

    bg_top = theme["bg_top"]
    bg_bottom = theme["bg_bottom"]
    accent = theme["accent"]
    accent2 = theme["accent2"]
    text_color = theme["text"]
    subtext = theme["subtext"]

    # --- Фон ---
    img = Image.new("RGB", (CARD_W, CARD_H), bg_top)
    _draw_gradient(img, bg_top, bg_bottom)
    img = img.convert("RGBA")

    # Свечения
    _draw_glow_circle(img, (150, 150), 280, accent, alpha=45)
    _draw_glow_circle(img, (CARD_W - 100, CARD_H - 250), 300, accent2, alpha=35)
    _draw_glow_circle(img, (CARD_W - 200, 400), 180, accent, alpha=25)

    draw = ImageDraw.Draw(img)

    # Боковая полоса
    draw.rectangle(
        [(0, 0), (5, CARD_H)],
        fill=(accent[0], accent[1], accent[2], 230),
    )

    # --- Шапка: бренд ---
    font_brand = _load_font(24, bold=True)
    font_brand_sub = _load_font(14)
    draw.text((60, 55), "ВАЙБМИ", font=font_brand, fill=accent)
    draw.text((60, 85), "узнай свой вайб", font=font_brand_sub, fill=subtext)

    # --- Заголовок «ТВОЙ ВАЙБ-МЕСЯЦ» ---
    font_title = _load_font(44, bold=True)
    title_text = "Т В О Й   В А Й Б - М Е С Я Ц"
    title_w = _text_width(draw, title_text, font_title)
    if title_w > CARD_W - 120:
        font_title = _load_font(36, bold=True)
        title_w = _text_width(draw, title_text, font_title)
    draw.text(
        ((CARD_W - title_w) // 2, 165),
        title_text,
        font=font_title,
        fill=text_color,
    )

    # Подзаголовок (период)
    if period_label:
        font_period = _load_font(18)
        pw = _text_width(draw, period_label, font_period)
        draw.text(
            ((CARD_W - pw) // 2, 225),
            period_label,
            font=font_period,
            fill=subtext,
        )

    # --- Summary (плашка с фразой от AI) ---
    font_summary = _load_font(28, bold=True)
    summary_text = summary or "Твой вайб растёт"
    if len(summary_text) > 100:
        summary_text = summary_text[:97] + "…"

    summary_lines = _wrap_text(draw, summary_text, font_summary, CARD_W - 200)
    line_h = 40
    summary_box_h = max(80, len(summary_lines) * line_h + 50)

    sx1, sy1 = 80, 280
    sx2, sy2 = CARD_W - 80, sy1 + summary_box_h

    overlay = Image.new("RGBA", (CARD_W, CARD_H), (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)
    odraw.rounded_rectangle(
        [(sx1, sy1), (sx2, sy2)],
        radius=20,
        fill=(accent[0], accent[1], accent[2], 35),
        outline=(accent[0], accent[1], accent[2], 220),
        width=3,
    )
    img.alpha_composite(overlay)

    ty = sy1 + 25
    for line in summary_lines:
        lw = _text_width(draw, line, font_summary)
        draw.text(
            ((CARD_W - lw) // 2, ty),
            line,
            font=font_summary,
            fill=text_color,
        )
        ty += line_h

    # --- Сетка плиток 2×3 ---
    grid_top = sy2 + 40
    tile_w = 360
    tile_h = 110
    gap_x = 40
    gap_y = 25

    total_grid_w = tile_w * 2 + gap_x
    grid_left = (CARD_W - total_grid_w) // 2

    tiles = [
        ("charisma", "Анализов", str(stats.get("total_analyses", 0))),
        ("energy", "Очков", str(stats.get("total_points", 0))),
        ("humor", "Стрик", f"{stats.get('current_streak', 0)} дн."),
        ("intellect", "Активных дней", f"{stats.get('active_days', 0)}/7"),
        ("creativity", "Архетипов", str(stats.get("unique_archetypes", 0))),
        ("chaos", "Легендарных", str(stats.get("legendary_count", 0))),
    ]

    for idx, (icon_key, label, value) in enumerate(tiles):
        row = idx // 2
        col = idx % 2
        tx = grid_left + col * (tile_w + gap_x)
        ty = grid_top + row * (tile_h + gap_y)
        _draw_stat_tile(
            img, tx, ty, tile_w, tile_h,
            icon_key, label, value, theme,
        )

    # --- Футер ---
    footer_y = CARD_H - 70
    font_slogan = _load_font(20, bold=True)
    draw.text((60, footer_y), "ВАЙБМИ", font=font_slogan, fill=accent)

    font_slogan_sub = _load_font(13)
    draw.text(
        (60, footer_y + 28),
        "· твой вайб-месяц",
        font=font_slogan_sub,
        fill=subtext,
    )

    if bot_username:
        bot_str = f"@{bot_username}"
        font_bot = _load_font(18)
        bw = _text_width(draw, bot_str, font_bot)
        draw.text(
            (CARD_W - bw - 60, footer_y + 8),
            bot_str,
            font=font_bot,
            fill=subtext,
        )

    # Нижняя полоса
    draw.rectangle(
        [(0, CARD_H - 4), (CARD_W, CARD_H)],
        fill=(accent[0], accent[1], accent[2], 255),
    )

    buf = BytesIO()
    img.convert("RGB").save(buf, format="PNG", optimize=True)
    return buf.getvalue()