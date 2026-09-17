from typing import Optional

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select

from database.connection import async_session
from database.models import User
from utils.logging import get_logger

router = Router()
logger = get_logger(__name__)


# ============================================================
# Клавиатура
# ============================================================
def _privacy_kb(user: User) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text=f"{'✅' if user.show_profile else '❌'} Показывать профиль",
                callback_data="toggle_show_profile",
            )],
            [InlineKeyboardButton(
                text=f"{'✅' if user.show_photo else '❌'} Показывать фото",
                callback_data="toggle_show_photo",
            )],
            [InlineKeyboardButton(
                text=f"{'✅' if user.show_username else '❌'} Показывать username",
                callback_data="toggle_show_username",
            )],
            [InlineKeyboardButton(
                text=f"{'✅' if user.allow_messages else '❌'} Разрешать сообщения",
                callback_data="toggle_allow_messages",
            )],
            [InlineKeyboardButton(text="⬅️ Назад в настройки", callback_data="settings")],
        ]
    )


# ============================================================
# Хелперы
# ============================================================
async def _get_user(telegram_id: int) -> Optional[User]:
    async with async_session() as session:
        return (await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )).scalar_one_or_none()


async def _show_privacy(callback: CallbackQuery) -> None:
    """Отправляет или обновляет сообщение с меню приватности."""
    user = await _get_user(callback.from_user.id)
    if user is None:
        await callback.message.answer(
            "Сначала отправь фото — создай профиль!"
        )
        return

    text = (
        "⚙️ <b>Настройки приватности</b>\n\n"
        "Управляй тем, что видят другие игроки:"
    )
    kb = _privacy_kb(user)

    # Пытаемся отредактировать текущее сообщение, иначе шлём новое
    try:
        await callback.message.edit_text(text, reply_markup=kb)
    except Exception:
        await callback.message.answer(text, reply_markup=kb)


# ============================================================
# Хендлеры
# ============================================================
@router.callback_query(F.data == "privacy_settings")
async def cb_privacy_settings(callback: CallbackQuery):
    await callback.answer()
    await _show_privacy(callback)


@router.callback_query(F.data.startswith("toggle_"))
async def cb_toggle(callback: CallbackQuery):
    field = callback.data.replace("toggle_", "")

    allowed_fields = {
        "show_profile",
        "show_photo",
        "show_username",
        "allow_messages",
    }
    if field not in allowed_fields:
        await callback.answer("Неизвестная настройка")
        return

    async with async_session() as session:
        user = (await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )).scalar_one_or_none()

        if user is None:
            await callback.answer("Профиль не найден")
            return

        setattr(user, field, not getattr(user, field))
        new_value = getattr(user, field)
        await session.commit()

    # Всплывающее уведомление
    await callback.answer("Включено ✅" if new_value else "Отключено ❌")

    # Обновляем клавиатуру — берём свежего user вне сессии
    user = await _get_user(callback.from_user.id)
    if user:
        try:
            await callback.message.edit_reply_markup(reply_markup=_privacy_kb(user))
        except Exception:
            pass