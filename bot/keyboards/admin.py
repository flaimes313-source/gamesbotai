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
            [
                InlineKeyboardButton(text="📨 Рассылка", callback_data="adm_broadcast"),
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
            [InlineKeyboardButton(text="📊 Сводка по всем", callback_data="subs_summary")],
            [InlineKeyboardButton(text="➕ Новая кампания", callback_data="subs_new")],
            [InlineKeyboardButton(text="🚨 Стоп всё", callback_data="subs_stop_all")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="adm_back")],
        ]
    )


def subs_campaign_card_kb(campaign_id: int, is_active: bool) -> InlineKeyboardMarkup:
    """
    Клавиатура карточки кампании.
    Кнопка «Остановить» — только если кампания активна.
    """
    rows = [
        [InlineKeyboardButton(
            text="📋 Подписчики",
            callback_data=f"subs_subs_{campaign_id}",
        )],
        [InlineKeyboardButton(
            text="📊 Разбивка по дням",
            callback_data=f"subs_daily_{campaign_id}",
        )],
        [InlineKeyboardButton(
            text="📤 Экспорт CSV",
            callback_data=f"subs_export_{campaign_id}",
        )],
        [InlineKeyboardButton(
            text="🔄 Обновить",
            callback_data=f"subs_card_{campaign_id}",
        )],
    ]
    if is_active:
        rows.append([InlineKeyboardButton(
            text="⏸ Остановить кампанию",
            callback_data=f"subs_stop_{campaign_id}",
        )])
    rows.append([InlineKeyboardButton(
        text="⬅️ К списку",
        callback_data="subs_list",
    )])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def subs_subscribers_kb(campaign_id: int, page: int, has_next: bool = False) -> InlineKeyboardMarkup:
    """
    Клавиатура списка подписчиков.
    """
    rows = []

    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data=f"subs_subs_{campaign_id}_p{page - 1}",
        ))
    if has_next:
        nav.append(InlineKeyboardButton(
            text="Вперёд ➡️",
            callback_data=f"subs_subs_{campaign_id}_p{page + 1}",
        ))
    if nav:
        rows.append(nav)

    rows.append([InlineKeyboardButton(
        text="📤 Экспорт CSV",
        callback_data=f"subs_export_{campaign_id}",
    )])
    rows.append([InlineKeyboardButton(
        text="⬅️ К кампании",
        callback_data=f"subs_card_{campaign_id}",
    )])

    return InlineKeyboardMarkup(inline_keyboard=rows)


def subs_back_kb() -> InlineKeyboardMarkup:
    """Возврат к списку кампаний."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ К списку", callback_data="subs_list")],
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
def flags_menu_kb(flags: dict) -> InlineKeyboardMarkup:
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
# ЧАТЫ
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


# ============================================================
# РАССЫЛКА
# ============================================================
def broadcast_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✍️ Только текст", callback_data="bc_type_text")],
            [InlineKeyboardButton(text="🖼 Только картинка", callback_data="bc_type_photo")],
            [InlineKeyboardButton(text="🖼+✍️ Картинка + текст", callback_data="bc_type_photo_text")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="adm_back")],
        ]
    )


def broadcast_add_button_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="🔗 Добавить кнопку со ссылкой",
                callback_data="bc_add_button",
            )],
            [InlineKeyboardButton(
                text="➡️ Без кнопки, дальше",
                callback_data="bc_no_button",
            )],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="bc_cancel")],
        ]
    )


def broadcast_cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="bc_cancel")],
        ]
    )


def broadcast_confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🚀 Отправить всем", callback_data="bc_confirm")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="bc_cancel")],
        ]
    )