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
                KeyboardButton(text="📬 Входящие"),
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
    """
    Кнопка «Поделиться» сначала вызывается как callback (для трекинга),
    потом бот возвращает сообщение с реальной share-ссылкой.
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📤 Поделиться с друзьями", callback_data="do_share")],
        ]
    )


def share_link_kb(share_url: str) -> InlineKeyboardMarkup:
    """Inline-кнопка с готовой ссылкой шаринга (открывает системный share)."""
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
            [InlineKeyboardButton(text="🎮 Социальная игра", callback_data="game_menu")],
            [InlineKeyboardButton(text="💎 PRO", callback_data="pro_menu")],
            [InlineKeyboardButton(text="🆘 Поддержка", callback_data="support_menu")],
            [InlineKeyboardButton(text="🏠 В главное меню", callback_data="back_to_main")],
        ]
    )


# ============================================================
# PRO
# ============================================================
def pro_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💎 Купить PRO (299 ₽ / 30 дней)", callback_data="buy_pro")],
            [InlineKeyboardButton(text="🎟 Ввести промокод", callback_data="enter_promo")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="settings")],
        ]
    )


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