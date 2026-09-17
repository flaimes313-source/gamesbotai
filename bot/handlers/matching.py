from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from bot.keyboards.matching import match_actions_kb, modes_kb
from config import config
from database.connection import async_session
from database.models import Profile, User
from sqlalchemy import select
from services.matching.compatibility import compatibility_score
from services.matching.matcher import find_candidates
from utils.logging import get_logger

router = Router()
logger = get_logger(__name__)


async def _my_user_id(telegram_id: int) -> int | None:
    async with async_session() as session:
        user = (await session.execute(select(User).where(User.telegram_id == telegram_id))).scalar_one_or_none()
        return user.id if user else None


@router.message(F.text == "🎯 Найти игроков")
async def find_players(message: Message):
    if not config.MATCHING_ENABLED:
        await message.answer("Поиск игроков временно отключён.")
        return
    await message.answer("Выбери режим поиска:", reply_markup=modes_kb())


@router.callback_query(F.data.startswith("mode_"))
async def mode_selected(callback: CallbackQuery):
    await callback.answer()
    if not config.MATCHING_ENABLED:
        await callback.message.answer("Поиск игроков отключён.")
        return

    mode = callback.data.replace("mode_", "")
    me_id = await _my_user_id(callback.from_user.id)
    if me_id is None:
        await callback.message.answer("Сначала отправь фото и создай профиль!")
        return

    async with async_session() as session:
        candidates = await find_candidates(session, me_id, mode=mode, limit=5)

    if not candidates:
        await callback.message.answer("Пока нет игроков с подходящими профилями. Загляни позже!")
        return

    for c in candidates:
        p = c["profile"]
        username_str = f"@{c['username']}" if (c["username"] and c["show_username"]) else "Скрыт"
        text = (
            f"🎯 Совпадение: <b>{c['score']}%</b>\n"
            f"🧨 {p['archetype']}\n"
            f"Харизма {p['charisma']} · Юмор {p['humor']} · Хаос {p['chaos']}\n"
            f"Username: {username_str}"
        )
        await callback.message.answer(text, reply_markup=match_actions_kb(c["user_id"]))


@router.callback_query(F.data == "find_players")
async def cb_find_players(callback: CallbackQuery):
    await callback.answer()
    await callback.message.answer("Выбери режим поиска:", reply_markup=modes_kb())