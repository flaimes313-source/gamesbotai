from aiogram import F, Router
from aiogram.types import Message
from sqlalchemy import select

from database.connection import async_session
from database.models import User
from services.achievements import list_user_achievements

router = Router()


@router.message(F.text == "🏆 Достижения")
async def show_achievements(message: Message):
    async with async_session() as session:
        user = (await session.execute(select(User).where(User.telegram_id == message.from_user.id))).scalar_one_or_none()

    if user is None:
        await message.answer("Сначала пройди анализ!")
        return

    achievements = await list_user_achievements(user.id)
    if not achievements:
        await message.answer("🏆 Пока нет достижений. Отправь фото и поделись результатом!")
        return

    lines = ["🏆 <b>Мои достижения</b>\n"]
    for a in achievements:
        lines.append(f"{a.emoji} <b>{a.title}</b> — {a.description}")
    await message.answer("\n".join(lines))