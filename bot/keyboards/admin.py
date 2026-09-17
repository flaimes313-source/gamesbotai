from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def admin_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📊 Статистика", callback_data="adm_stats")],
            [InlineKeyboardButton(text="📉 Воронка", callback_data="adm_funnel")],
            [InlineKeyboardButton(text="🧪 A/B тесты", callback_data="adm_ab")],
            [InlineKeyboardButton(text="👥 Пользователи", callback_data="adm_users")],
            [InlineKeyboardButton(text="⭐ Белый список", callback_data="adm_wl")],
            [InlineKeyboardButton(text="📢 Реклама", callback_data="adm_ads")],
            [InlineKeyboardButton(text="📣 Обязательные подписки", callback_data="adm_subs")],
            [InlineKeyboardButton(text="💰 Платежи", callback_data="adm_pay")],
            [InlineKeyboardButton(text="🎟 Промокоды", callback_data="adm_promos")],
            [InlineKeyboardButton(text="⚙️ Feature flags", callback_data="adm_flags")],
            [InlineKeyboardButton(text="🆘 Поддержка", callback_data="adm_support")],
        ]
    )


def ads_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📋 Список кампаний", callback_data="ads_list")],
            [InlineKeyboardButton(text="➕ Новая кампания", callback_data="ads_new")],
            [InlineKeyboardButton(text="🚨 Стоп всё", callback_data="ads_stop_all")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="adm_back")],
        ]
    )


def subs_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📋 Список кампаний", callback_data="subs_list")],
            [InlineKeyboardButton(text="➕ Новая кампания", callback_data="subs_new")],
            [InlineKeyboardButton(text="🚨 Стоп всё", callback_data="subs_stop_all")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="adm_back")],
        ]
    )


def promos_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📋 Список промокодов", callback_data="promos_list")],
            [InlineKeyboardButton(text="➕ Новый промокод", callback_data="promos_new")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="adm_back")],
        ]
    )


def flags_menu_kb(flags: dict[str, bool]) -> InlineKeyboardMarkup:
    rows = []
    for key, value in flags.items():
        emoji = "✅" if value else "❌"
        rows.append([InlineKeyboardButton(
            text=f"{emoji} {key}",
            callback_data=f"flag_toggle_{key}",
        )])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="adm_back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)