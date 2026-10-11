from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def profile_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🔄 Новый анализ", callback_data="new_analysis"),
                InlineKeyboardButton(text="📈 Моя динамика", callback_data="my_dynamics"),
            ],
            [
                InlineKeyboardButton(text="🧠 Мой вайб-отчёт", callback_data="vibe_report"),
                InlineKeyboardButton(text="💥 Совместимость", callback_data="compat_run"),
            ],
            [
                InlineKeyboardButton(text="🧪 Пройти тест", callback_data="tests_menu"),
                InlineKeyboardButton(text="👥 Сравнить", callback_data="compare_menu"),
            ],
            [
                InlineKeyboardButton(text="🎯 Найти игроков", callback_data="find_players"),
                InlineKeyboardButton(text="💬 Мои чаты", callback_data="chat_list"),
            ],
            [
                InlineKeyboardButton(text="📊 Моя статистика", callback_data="my_stats"),
                InlineKeyboardButton(text="📤 Поделиться", callback_data="share_profile"),
            ],
            [
                InlineKeyboardButton(text="⚙️ Настройки", callback_data="settings"),
            ],
        ]
    )