from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)


# ============================================================
# ГЛАВНОЕ REPLY-МЕНЮ (постоянные кнопки внизу экрана)
# ============================================================
def main_menu_kb() -> ReplyKeyboardMarkup:
    """
    Основное меню бота. Показывается после /start и остаётся
    внизу экрана как reply-клавиатура.
    """
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="👤 Мой профиль"),
                KeyboardButton(text="📸 Новый анализ"),
            ],
            [
                KeyboardButton(text="👥 Сравнить"),
                KeyboardButton(text="🎯 Найти игроков"),
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
    """Inline-кнопка для приглашения отправить фото."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📸 Отправить фото", callback_data="send_photo")],
        ]
    )


# ============================================================
# SHARE
# ============================================================
def share_kb(share_url: str) -> InlineKeyboardMarkup:
    """
    Клавиатура после результата анализа:
    кнопка «Поделиться» (открывает системный share Telegram)
    и «Новый анализ».
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📤 Поделиться с друзьями", url=share_url)],
            [InlineKeyboardButton(text="🔄 Новый анализ", callback_data="new_analysis")],
        ]
    )


def share_only_kb(share_url: str) -> InlineKeyboardMarkup:
    """Только кнопка «Поделиться» (для профиля)."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📤 Поделиться с друзьями", url=share_url)],
        ]
    )


# ============================================================
# НАСТРОЙКИ
# ============================================================
def settings_kb() -> InlineKeyboardMarkup:
    """Меню настроек."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⚙️ Приватность", callback_data="privacy_settings")],
            [InlineKeyboardButton(text="🎮 Социальная игра", callback_data="game_menu")],
            [InlineKeyboardButton(text="💎 PRO", callback_data="pro_menu")],
            [InlineKeyboardButton(text="🆘 Поддержка", callback_data="support_menu")],
        ]
    )


# ============================================================
# PRO
# ============================================================
def pro_menu_kb() -> InlineKeyboardMarkup:
    """Меню PRO-подписки."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💎 Купить PRO (299 ₽ / 30 дней)", callback_data="buy_pro")],
            [InlineKeyboardButton(text="🎟 Ввести промокод", callback_data="enter_promo")],
        ]
    )


# ============================================================
# ДОСТИЖЕНИЯ
# ============================================================
def achievements_back_kb() -> InlineKeyboardMarkup:
    """Кнопка «назад» из достижений."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🏠 В главное меню", callback_data="back_to_main")],
        ]
    )


# ============================================================
# ПОДДЕРЖКА
# ============================================================
def support_kb() -> InlineKeyboardMarkup:
    """Меню поддержки."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✍️ Написать в поддержку", callback_data="support_write")],
            [InlineKeyboardButton(text="📖 FAQ", callback_data="support_faq")],
        ]
    )


# ============================================================
# УТИЛИТА
# ============================================================
def back_to_main_kb() -> InlineKeyboardMarkup:
    """Универсальная кнопка возврата в главное меню."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🏠 В главное меню", callback_data="back_to_main")],
        ]
    )


def cancel_kb() -> InlineKeyboardMarkup:
    """Универсальная кнопка «Отмена»."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_action")],
        ]
    )