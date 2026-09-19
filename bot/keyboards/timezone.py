from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from services.timezones import POPULAR_TIMEZONES


def timezone_menu_kb(page: int = 0, per_page: int = 8) -> InlineKeyboardMarkup:
    """
    Клавиатура выбора часового пояса с пагинацией.
    """
    total = len(POPULAR_TIMEZONES)
    start = page * per_page
    end = start + per_page

    rows = []
    for tz_name, label in POPULAR_TIMEZONES[start:end]:
        rows.append([InlineKeyboardButton(
            text=label,
            callback_data=f"tz_set_{tz_name}",
        )])

    # Пагинация
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"tz_page_{page - 1}"))
    if end < total:
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"tz_page_{page + 1}"))
    if nav:
        rows.append(nav)

    return InlineKeyboardMarkup(inline_keyboard=rows)