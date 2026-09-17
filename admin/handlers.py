from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message, InlineKeyboardButton, InlineKeyboardMarkup

from bot.keyboards.admin import admin_menu_kb
from config import config
from database.connection import async_session
from database.models import User
from services.metrics import full_stats
from sqlalchemy import select
from utils.logging import get_logger

router = Router()
logger = get_logger(__name__)


def _is_admin(telegram_id: int) -> bool:
    return telegram_id in config.ADMIN_IDS


@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if not _is_admin(message.from_user.id):
        return
    await message.answer("🛠 <b>Админ-панель</b>", reply_markup=admin_menu_kb())


@router.callback_query(F.data == "adm_stats")
async def cb_stats(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id):
        await callback.answer("Нет доступа")
        return
    await callback.answer()

    stats = await full_stats()
    text = (
        f"📊 <b>BOT STATS</b>\n\n"
        f"👥 Users: {stats['users']}\n"
        f"📈 DAU: {stats['dau']}\n"
        f"🆕 New today: {stats['new']}\n\n"
        f"📸 Analyses: {stats['analyses']}\n"
        f"🎯 Matches: {stats['matches']}\n"
        f"💬 Messages: {stats['messages']}\n"
        f"🧪 Tests: {stats['tests']}\n\n"
        f"💰 PRO revenue: {stats['pro_revenue']:.2f} ₽"
    )
    await callback.message.answer(text)


@router.callback_query(F.data == "adm_users")
async def cb_users(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id):
        await callback.answer("Нет доступа")
        return
    await callback.answer()

    async with async_session() as session:
        users = (await session.execute(select(User).order_by(User.id.desc()).limit(20))).scalars().all()

    lines = ["👥 <b>Последние 20 пользователей</b>\n"]
    for u in users:
        lines.append(f"• {u.telegram_id} @{u.username or '—'} (game={u.participates_in_game})")
    await callback.message.answer("\n".join(lines))


@router.callback_query(F.data.startswith("adm_"))
async def cb_other(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id):
        await callback.answer("Нет доступа")
        return
    await callback.answer("Раздел в разработке 🙂")