from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def admin_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📊 Статистика", callback_data="adm_stats")],
            [InlineKeyboardButton(text="👥 Пользователи", callback_data="adm_users")],
            [InlineKeyboardButton(text="⭐ Белый список", callback_data="adm_wl")],
            [InlineKeyboardButton(text="📢 Реклама", callback_data="adm_ads")],
            [InlineKeyboardButton(text="📣 Обязательные подписки", callback_data="adm_subs")],
            [InlineKeyboardButton(text="💰 Платежи", callback_data="adm_pay")],
            [InlineKeyboardButton(text="💎 PRO", callback_data="adm_pro")],
            [InlineKeyboardButton(text="🆘 Поддержка", callback_data="adm_support")],
            [InlineKeyboardButton(text="⚙️ Настройки", callback_data="adm_settings")],
        ]
    )