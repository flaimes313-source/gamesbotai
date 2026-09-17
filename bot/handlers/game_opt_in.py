from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select

from database.connection import async_session
from database.models import User

router = Router()


def game_menu_kb(is_in_game: bool) -> InlineKeyboardMarkup:
    if is_in_game:
        kb = [
            [InlineKeyboardButton(text="🎯 Найти игроков", callback_data="find_players")],
            [InlineKeyboardButton(text="⚙️ Настройки приватности", callback_data="privacy_settings")],
            [InlineKeyboardButton(text="🚪 Выйти из игры", callback_data="game_leave")],
        ]
    else:
        kb = [
            [InlineKeyboardButton(text="🎮 Войти в социальную игру", callback_data="game_join")],
        ]
    return InlineKeyboardMarkup(inline_keyboard=kb)


@router.message(F.text == "🎮 Социальная игра")
async def game_menu(message: Message):
    async with async_session() as session:
        user = (await session.execute(select(User).where(User.telegram_id == message.from_user.id))).scalar_one_or_none()

    if user is None:
        await message.answer("Сначала отправь фото!")
        return

    await message.answer(
        "🎮 Социальная игра\n\n"
        "Здесь можно искать других игроков по архетипу, харизме и хаосу.\n"
        "Управляй приватностью в настройках.",
        reply_markup=game_menu_kb(user.participates_in_game),
    )


@router.callback_query(F.data == "game_join")
async def game_join(callback: CallbackQuery):
    await callback.answer()
    async with async_session() as session:
        user = (await session.execute(select(User).where(User.telegram_id == callback.from_user.id))).scalar_one_or_none()
        if user:
            user.participates_in_game = True
            await session.commit()
    await callback.message.answer("✅ Ты в игре! Теперь тебя могут найти другие игроки.")


@router.callback_query(F.data == "game_leave")
async def game_leave(callback: CallbackQuery):
    await callback.answer()
    async with async_session() as session:
        user = (await session.execute(select(User).where(User.telegram_id == callback.from_user.id))).scalar_one_or_none()
        if user:
            user.participates_in_game = False
            await session.commit()
    await callback.message.answer("🚪 Ты вышел из игры. Можешь вернуться в любой момент.")


@router.callback_query(F.data == "privacy_settings")
async def privacy_settings(callback: CallbackQuery):
    await callback.answer()
    await callback.message.answer(
        "⚙️ Настройки приватности будут доступны в следующем обновлении."
    )