from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy import select

from database.connection import async_session
from database.models import Profile, User
from utils.logging import get_logger

router = Router()
logger = get_logger(__name__)


@router.callback_query(F.data == "compare_menu")
async def cb_compare(callback: CallbackQuery):
    await callback.answer()
    async with async_session() as session:
        user = (await session.execute(select(User).where(User.telegram_id == callback.from_user.id))).scalar_one_or_none()
        if user is None or user.referrer_id is None:
            await callback.message.answer(
                "Сравнение доступно, когда друг придёт по твоей ссылке. Поделись результатом!"
            )
            return

        referrer = (await session.execute(select(User).where(User.id == user.referrer_id))).scalar_one_or_none()
        if referrer is None:
            await callback.message.answer("Не удалось найти друга 😔")
            return

        my_p = (await session.execute(select(Profile).where(Profile.user_id == user.id).order_by(Profile.id.desc()).limit(1))).scalar_one_or_none()
        fr_p = (await session.execute(select(Profile).where(Profile.user_id == referrer.id).order_by(Profile.id.desc()).limit(1))).scalar_one_or_none()

    if not my_p or not fr_p:
        await callback.message.answer("У кого-то из вас пока нет профиля.")
        return

    diff = abs(my_p.chaos - fr_p.chaos)
    text = (
        f"👥 <b>СРАВНИТЬ С ДРУГОМ</b>\n\n"
        f"Ты: 🧨 Хаос {my_p.chaos}\n"
        f"Друг: 🧊 Хаос {fr_p.chaos}\n\n"
        f"Разница: {diff} пунктов 😂\n\n"
        f"🏆 Кто харизматичнее: "
        f"{'ты' if my_p.charisma > fr_p.charisma else 'друг'}\n"
        f"😂 Кто смешнее: "
        f"{'ты' if my_p.humor > fr_p.humor else 'друг'}\n"
        f"🧠 Кто интеллектуальнее: "
        f"{'ты' if my_p.intellect > fr_p.intellect else 'друг'}"
    )
    await callback.message.answer(text)