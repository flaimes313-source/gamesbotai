from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy import func, select

from bot.keyboards.admin import admin_menu_kb
from config import config
from database.connection import async_session
from database.models import Match, PhotoAnalysis, Profile, User
from utils.logging import get_logger

router = Router()
logger = get_logger(__name__)


def _is_admin(telegram_id: int) -> bool:
    return telegram_id in config.ADMIN_IDS


@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if not _is_admin(message.from_user.id):
        return
    await message.answer("🛠 Админ-панель", reply_markup=admin_menu_kb())


@router.callback_query(F.data == "adm_stats")
async def cb_stats(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id):
        await callback.answer("Нет доступа")
        return
    await callback.answer()

    async with async_session() as session:
        users_total = (await session.execute(select(func.count(User.id)))).scalar_one()
        users_game = (await session.execute(select(func.count(User.id)).where(User.participates_in_game.is_(True)))).scalar_one()
        profiles_total = (await session.execute(select(func.count(Profile.id)))).scalar_one()
        analyses_total = (await session.execute(select(func.count(PhotoAnalysis.id)))).scalar_one()
        matches_total = (await session.execute(select(func.count(Match.id)))).scalar_one()

    text = (
        f"📊 <b>Статистика</b>\n\n"
        f"👥 Пользователей: {users_total}\n"
        f"🎮 В игре: {users_game}\n"
        f"👤 Профилей: {profiles_total}\n"
        f"📸 Анализов: {analyses_total}\n"
        f"🎯 Матчей: {matches_total}"
    )
    await callback.message.answer(text)


@router.callback_query(F.data.startswith("adm_"))
async def cb_other(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id):
        await callback.answer("Нет доступа")
        return
    await callback.answer("Раздел появится позже 🙂")