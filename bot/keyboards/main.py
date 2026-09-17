from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton


def main_menu_kb() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="👤 Мой профиль"), KeyboardButton(text="📸 Новый анализ")],
            [KeyboardButton(text="👥 Сравнить"), KeyboardButton(text="🎯 Найти игроков")],
            [KeyboardButton(text="📤 Поделиться"), KeyboardButton(text="🏆 Достижения")],
            [KeyboardButton(text="⚙️ Настройки"), KeyboardButton(text="🆘 Поддержка")],
        ],
        resize_keyboard=True,
    )
    return kb


def send_photo_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📸 Отправить фото", callback_data="send_photo")]
        ]
    )


def share_kb(share_url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📤 Поделиться с друзьями", url=share_url)],
            [InlineKeyboardButton(text="🔄 Новый анализ", callback_data="new_analysis")],
        ]
    )