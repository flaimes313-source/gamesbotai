from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)


# ============================================================
# ГЛАВНОЕ REPLY-МЕНЮ
# ============================================================
def main_menu_kb() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="👤 Мой профиль"),
                KeyboardButton(text="🎯 Найти игроков"),
            ],
            [
                KeyboardButton(text="👥 Сравнить"),
                KeyboardButton(text="💬 Мои чаты"),
            ],
            [
                KeyboardButton(text="🎮 Социальная игра"),
                KeyboardButton(text="🏆 Достижения"),
            ],
            [
                KeyboardButton(text="💎 PRO"),
                KeyboardButton(text="📤 Поделиться"),
            ],
            [
                KeyboardButton(text="⚙️ Настройки"),
                KeyboardButton(text="🆘 Поддержка"),
            ],
        ],
        resize_keyboard=True,
        input_field_placeholder="Отправь фото или выбери пункт меню 👇",
    )
    return kb


# ============================================================
# ОТПРАВКА ФОТО
# ============================================================
def send_photo_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📸 Отправить фото", callback_data="send_photo")],
        ]
    )


# ============================================================
# SHARE
# ============================================================
def share_kb(share_url: str = "") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="📤 Поделиться с друзьями",
                callback_data="do_share",
            )],
            [InlineKeyboardButton(
                text="🔄 Новый анализ",
                callback_data="new_analysis",
            )],
        ]
    )


def share_link_kb(share_url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📤 Открыть шаринг", url=share_url)],
        ]
    )


def share_only_kb(share_url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📤 Поделиться с друзьями", url=share_url)],
        ]
    )


# ============================================================
# НАСТРОЙКИ
# ============================================================
def settings_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⚙️ Приватность", callback_data="privacy_settings")],
            [InlineKeyboardButton(text="🌍 Часовой пояс", callback_data="tz_menu")],
            [InlineKeyboardButton(text="🎮 Социальная игра", callback_data="game_menu")],
            [InlineKeyboardButton(text="💎 PRO", callback_data="pro_menu")],
            [InlineKeyboardButton(text="🆘 Поддержка", callback_data="support_menu")],
            [InlineKeyboardButton(text="🏠 В главное меню", callback_data="back_to_main")],
        ]
    )


# ============================================================
# PRO
# ============================================================
def pro_menu_kb(is_premium: bool = False) -> InlineKeyboardMarkup:
    """
    Меню PRO.
    - 1 месяц: 390 ₽
    - 6 месяцев: 1990 ₽ (-15%)
    - 12 месяцев: 3490 ₽ (-25%)
    """
    rows = []

    if is_premium:
        rows.append([InlineKeyboardButton(
            text="💎 Продлить на 1 мес (390 ₽)",
            callback_data="buy_pro_1m",
        )])
    else:
        rows.append([InlineKeyboardButton(
            text="💎 Подключить на 1 мес (390 ₽)",
            callback_data="buy_pro_1m",
        )])

    rows.append([InlineKeyboardButton(
        text="🔥 6 месяцев — 1990 ₽ (-15%)",
        callback_data="buy_pro_6m",
    )])
    rows.append([InlineKeyboardButton(
        text="🚀 12 месяцев — 3490 ₽ (-25%)",
        callback_data="buy_pro_12m",
    )])
    rows.append([InlineKeyboardButton(
        text="🎟 Ввести промокод",
        callback_data="enter_promo",
    )])
    rows.append([InlineKeyboardButton(
        text="🎁 Подарить PRO другу",
        callback_data="gift_pro",
    )])
    rows.append([InlineKeyboardButton(
        text="⬅️ Назад",
        callback_data="settings",
    )])

    return InlineKeyboardMarkup(inline_keyboard=rows)


# ============================================================
# ДОСТИЖЕНИЯ
# ============================================================
def achievements_back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🏠 В главное меню", callback_data="back_to_main")],
        ]
    )


# ============================================================
# ПОДДЕРЖКА
# ============================================================
def support_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✍️ Написать в поддержку", callback_data="support_write")],
            [InlineKeyboardButton(text="📖 FAQ", callback_data="support_faq")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="settings")],
        ]
    )


# ============================================================
# УТИЛИТЫ
# ============================================================
def back_to_main_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🏠 В главное меню", callback_data="back_to_main")],
        ]
    )


def cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_action")],
        ]
    )