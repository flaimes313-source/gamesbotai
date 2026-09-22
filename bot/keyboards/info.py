from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def info_menu_kb() -> InlineKeyboardMarkup:
    """Меню раздела "О боте"."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="🎯 Как работает бот",
                callback_data="info_how_it_works",
            )],
            [InlineKeyboardButton(
                text="⭐ Очки и уровни",
                callback_data="info_points",
            )],
            [InlineKeyboardButton(
                text="✨ Легендарные архетипы",
                callback_data="info_legendary",
            )],
            [InlineKeyboardButton(
                text="💎 Как получить PRO бесплатно",
                callback_data="info_free_pro",
            )],
            [InlineKeyboardButton(
                text="🎯 Челленджи и квесты",
                callback_data="info_challenges",
            )],
            [InlineKeyboardButton(
                text="🔥 Стрики (серия дней)",
                callback_data="info_streaks",
            )],
            [InlineKeyboardButton(
                text="👥 Друзья и награды",
                callback_data="info_referrals",
            )],
            [InlineKeyboardButton(
                text="💎 Что даёт PRO",
                callback_data="info_pro_benefits",
            )],
            [InlineKeyboardButton(
                text="🏠 В главное меню",
                callback_data="back_to_main",
            )],
        ]
    )


def info_back_kb() -> InlineKeyboardMarkup:
    """Кнопка возврата в меню "О боте"."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="⬅️ К разделам",
                callback_data="info_menu",
            )],
            [InlineKeyboardButton(
                text="🏠 В главное меню",
                callback_data="back_to_main",
            )],
        ]
    )


def info_action_kb() -> InlineKeyboardMarkup:
    """Возврат + быстрые действия."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="📊 Моя статистика",
                callback_data="my_stats",
            )],
            [InlineKeyboardButton(
                text="🎯 Челлендж дня",
                callback_data="challenge_today",
            )],
            [InlineKeyboardButton(
                text="⬅️ К разделам",
                callback_data="info_menu",
            )],
        ]
    )