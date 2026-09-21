"""
График динамики вайба.
Отдельный модуль — не трогает основной генератор карточек.
"""
import io
import logging
from io import BytesIO
from typing import List, Optional

from PIL import Image, ImageDraw, ImageFont

from services.cards.fonts_embedded import (
    get_bold_font_bytes,
    get_regular_font_bytes,
)
from services.cards.themes import theme_for

_logger = logging.getLogger(__name__)


CHART_W = 900
CHART_H = 420


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
        _logger.error(f"[CHART] truetype failed (size={size}): {e}")
        return ImageFont.load_default()


# ============================================================
# Утилиты
# ============================================================
def _draw_gradient_bg(img: Image.Image, top_color, bottom_color):
    draw = ImageDraw.Draw(img)
    for y in range(CHART_H):
        t = y / max(1, CHART_H - 1)
        r = int(top_color[0] + (bottom_color[0] - top_color[0]) * t)
        g = int(top_color[1] + (bottom_color[1] - top_color[1]) * t)
        b = int(top_color[2] + (bottom_color[2] - top_color[2]) * t)
        draw.line([(0, y), (CHART_W, y)], fill=(r, g, b))


def _text_width(draw, text, font):
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0]


def _map_value(value: int, v_min: int, v_max: int, y_top: int, y_bottom: int) -> int:
    """Маппит значение 0..100 в пиксель Y."""
    if v_max == v_min:
        return (y_top + y_bottom) // 2
    t = (value - v_min) / (v_max - v_min)
    return int(y_bottom - t * (y_bottom - y_top))


def _pad_range(history: List[int]) -> tuple:
    """Возвращает (v_min, v_max) с небольшим отступом, чтобы график не прилипал."""
    if not history:
        return 0, 100
    v_min = min(history)
    v_max = max(history)
    if v_max == v_min:
        # Все значения одинаковые — рисуем плоскую линию по центру
        return max(0, v_min - 10), min(100, v_max + 10)
    padding = max(5, int((v_max - v_min) * 0.15))
    return max(0, v_min - padding), min(100, v_max + padding)


# ============================================================
# Основная функция
# ============================================================
def generate_dynamics_chart(
    history: List[int],
    label: str,
    period: Optional[str] = None,
    archetype: Optional[str] = None,
    bot_username: Optional[str] = None,
) -> bytes:
    """
    Рисует график одной характеристики по истории значений.

    history — список значений (0..100) в хронологическом порядке.
    label — заголовок, например "🔥 ХАОС".
    period — строка периода "12.09 — 21.09".
    archetype — текущий архетип (для выбора темы).
    bot_username — @username для футера.
    """
    if not history:
        history = [0]

    # Тема — по текущему архетипу, с fallback
    theme = theme_for(archetype or "default")
    bg_top = theme.get("bg_top", (12, 12, 22))
    bg_bottom = theme.get("bg_bottom", (8, 8, 16))
    accent = theme.get("accent", (0, 200, 255))
    accent2 = theme.get("accent2", (180, 100, 255))
    text_color = theme.get("text", (240, 240, 245))
    subtext = theme.get("subtext", (140, 140, 160))

    # === Фон ===
    img = Image.new("RGB", (CHART_W, CHART_H), bg_top)
    _draw_gradient_bg(img, bg_top, bg_bottom)
    img = img.convert("RGBA")
    draw = ImageDraw.Draw(img)

    # Боковая полоса
    draw.rectangle(
        [(0, 0), (4, CHART_H)],
        fill=(accent[0], accent[1], accent[2], 220),
    )

    # === Заголовок ===
    font_title = _load_font(36, bold=True)
    font_sub = _load_font(16)
    font_axis = _load_font(14)

    draw.text((60, 30), label, font=font_title, fill=accent)

    if period:
        draw.text((60, 78), period, font=font_sub, fill=subtext)

    # Значение справа сверху (последнее)
    last_value = history[-1]
    last_str = str(last_value)
    lw = _text_width(draw, last_str, font_title)
    draw.text(
        (CHART_W - lw - 60, 30),
        last_str,
        font=font_title,
        fill=accent,
    )

    # === Область графика ===
    plot_left = 90
    plot_right = CHART_W - 70
    plot_top = 150
    plot_bottom = CHART_H - 90

    plot_w = plot_right - plot_left
    plot_h = plot_bottom - plot_top

    v_min, v_max = _pad_range(history)

    # === Сетка ===
    grid_lines = 4
    for i in range(grid_lines + 1):
        gy = plot_top + int(plot_h * i / grid_lines)
        draw.line(
            [(plot_left, gy), (plot_right, gy)],
            fill=(40, 40, 60, 180),
            width=1,
        )
        # Подпись значения
        val_at_line = int(v_max - (v_max - v_min) * i / grid_lines)
        draw.text(
            (plot_left - 45, gy - 8),
            str(val_at_line),
            font=font_axis,
            fill=subtext,
        )

    # === Линия графика ===
    n = len(history)
    if n == 1:
        # Одна точка — рисуем кружок по центру
        cx = (plot_left + plot_right) // 2
        cy = _map_value(history[0], v_min, v_max, plot_top, plot_bottom)
        r = 8
        draw.ellipse(
            [(cx - r, cy - r), (cx + r, cy + r)],
            fill=accent,
            outline=accent2,
            width=2,
        )
    else:
        step_x = plot_w / (n - 1) if n > 1 else 0

        points = []
        for i, v in enumerate(history):
            x = int(plot_left + step_x * i)
            y = _map_value(v, v_min, v_max, plot_top, plot_bottom)
            points.append((x, y))

        # Линия
        for i in range(len(points) - 1):
            draw.line(
                [points[i], points[i + 1]],
                fill=accent,
                width=4,
            )

        # Точки
        for i, (x, y) in enumerate(points):
            r = 7 if i == len(points) - 1 else 5
            # Внешний круг (accent2)
            draw.ellipse(
                [(x - r - 2, y - r - 2), (x + r + 2, y + r + 2)],
                fill=accent2,
            )
            # Внутренний круг (accent)
            draw.ellipse(
                [(x - r, y - r), (x + r, y + r)],
                fill=accent,
            )

    # === Подписи по X (номера анализов) ===
    if n > 1:
        for i in range(n):
            x = int(plot_left + (plot_w / (n - 1)) * i)
            num_str = str(i + 1)
            nw = _text_width(draw, num_str, font_axis)
            draw.text(
                (x - nw // 2, plot_bottom + 15),
                num_str,
                font=font_axis,
                fill=subtext,
            )

    # === Футер ===
    footer_y = CHART_H - 40
    font_brand = _load_font(16, bold=True)
    draw.text((60, footer_y), "ВАЙБМИ", font=font_brand, fill=accent)

    font_slogan = _load_font(12)
    draw.text(
        (60 + 90, footer_y + 3),
        "· динамика вайба",
        font=font_slogan,
        fill=subtext,
    )

    if bot_username:
        bot_str = f"@{bot_username}"
        font_bot = _load_font(14)
        bw = _text_width(draw, bot_str, font_bot)
        draw.text(
            (CHART_W - bw - 60, footer_y + 2),
            bot_str,
            font=font_bot,
            fill=subtext,
        )

    draw.rectangle(
        [(0, CHART_H - 4), (CHART_W, CHART_H)],
        fill=(accent[0], accent[1], accent[2], 255),
    )

    buf = BytesIO()
    img.convert("RGB").save(buf, format="PNG", optimize=True)
    return buf.getvalue()