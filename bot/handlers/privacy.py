from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select

from database.connection import async_session
from database.models import User

router = Router()


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
        ]
    )


@router.callback_query(F.data == "privacy_settings")
async def cb_privacy(callback: CallbackQuery):
    await callback.answer()
    async with async_session() as session:
        user = (await session.execute(select(User).where(User.telegram_id == callback.from_user.id))).scalar_one_or_none()

    if user is None:
        await callback.message.answer("Сначала отправь фото!")
        return

    await callback.message.answer("⚙️ Настройки приватности:", reply_markup=_privacy_kb(user))


@router.callback_query(F.data.startswith("toggle_"))
async def cb_toggle(callback: CallbackQuery):
    await callback.answer("Обновлено")
    field = callback.data.replace("toggle_", "")

    async with async_session() as session:
        user = (await session.execute(select(User).where(User.telegram_id == callback.from_user.id))).scalar_one_or_none()
        if user is None:
            return
        if hasattr(user, field):
            setattr(user, field, not getattr(user, field))
            await session.commit()

    await callback.message.edit_reply_markup(reply_markup=_privacy_kb(user))