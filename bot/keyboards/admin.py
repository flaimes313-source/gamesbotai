from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


# ============================================================
# ГЛАВНОЕ МЕНЮ АДМИНКИ
# ============================================================
def admin_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📊 Статистика", callback_data="adm_stats"),
                InlineKeyboardButton(text="📉 Воронка", callback_data="adm_funnel"),
            ],
            [
                InlineKeyboardButton(text="💬 Чаты", callback_data="adm_chats"),
                InlineKeyboardButton(text="🧪 A/B тесты", callback_data="adm_ab"),
            ],
            [
                InlineKeyboardButton(text="👥 Пользователи", callback_data="adm_users"),
                InlineKeyboardButton(text="⭐ Белый список", callback_data="adm_wl"),
            ],
            [
                InlineKeyboardButton(text="📢 Реклама", callback_data="adm_ads"),
                InlineKeyboardButton(text="📣 Подписки", callback_data="adm_subs"),
            ],
            [
                InlineKeyboardButton(text="💰 Платежи", callback_data="adm_pay"),
                InlineKeyboardButton(text="🎟 Промокоды", callback_data="adm_promos"),
            ],
            [
                InlineKeyboardButton(text="⚙️ Feature flags", callback_data="adm_flags"),
                InlineKeyboardButton(text="🆘 Поддержка", callback_data="adm_support"),
            ],
        ]
    )


# ============================================================
# РЕКЛАМА
# ============================================================
def ads_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📋 Список кампаний", callback_data="ads_list")],
            [InlineKeyboardButton(text="➕ Новая кампания", callback_data="ads_new")],
            [InlineKeyboardButton(text="📈 Отчёт по рекламе", callback_data="adm_ads_report")],
            [InlineKeyboardButton(text="🚨 Стоп всё", callback_data="ads_stop_all")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="adm_back")],
        ]
    )


# ============================================================
# ОБЯЗАТЕЛЬНЫЕ ПОДПИСКИ
# ============================================================
def subs_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📋 Список кампаний", callback_data="subs_list")],
            [InlineKeyboardButton(text="➕ Новая кампания", callback_data="subs_new")],
            [InlineKeyboardButton(text="🚨 Стоп всё", callback_data="subs_stop_all")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="adm_back")],
        ]
    )


# ============================================================
# ПРОМОКОДЫ
# ============================================================
def promos_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📋 Список промокодов", callback_data="promos_list")],
            [InlineKeyboardButton(text="➕ Новый промокод", callback_data="promos_new")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="adm_back")],
        ]
    )


# ============================================================
# FEATURE FLAGS
# ============================================================
def flags_menu_kb(flags: dict[str, bool]) -> InlineKeyboardMarkup:
    """
    Динамическая клавиатура — по кнопке на каждый флаг.
    ✅ — включён, ❌ — выключен.
    """
    rows = []
    for key, value in flags.items():
        emoji = "✅" if value else "❌"
        rows.append([InlineKeyboardButton(
            text=f"{emoji} {key}",
            callback_data=f"flag_toggle_{key}",
        )])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="adm_back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ============================================================
# ЧАТЫ (для раздела «💬 Чаты»)
# ============================================================
def chats_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📊 За 7 дней", callback_data="adm_chats_7")],
            [InlineKeyboardButton(text="📊 За 30 дней", callback_data="adm_chats_30")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="adm_back")],
        ]
    )


# ============================================================
# ПОДДЕРЖКА
# ============================================================
def support_ticket_kb(ticket_id: int) -> InlineKeyboardMarkup:
    """
    Кнопки под конкретным тикетом в админке.
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="💬 Ответить",
                callback_data=f"adm_reply_{ticket_id}",
            )],
            [InlineKeyboardButton(
                text="✅ Закрыть без ответа",
                callback_data=f"adm_close_{ticket_id}",
            )],
        ]
    )