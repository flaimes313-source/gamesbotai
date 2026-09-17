from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def profile_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Новый анализ", callback_data="new_analysis")],
            [InlineKeyboardButton(text="🧪 Пройти тест", callback_data="tests_menu")],
            [InlineKeyboardButton(text="👥 Сравнить с другом", callback_data="compare_menu")],
            [InlineKeyboardButton(text="🎯 Найти игроков", callback_data="find_players")],
            [InlineKeyboardButton(text="📤 Поделиться", callback_data="share_profile")],
            [InlineKeyboardButton(text="⚙️ Настройки", callback_data="settings")],
        ]
    )