from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy import select

from database.connection import async_session
from database.models import Profile, User

router = Router()


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

    categories = [
        ("Харизма", my_p.charisma, fr_p.charisma),
        ("Юмор", my_p.humor, fr_p.humor),
        ("Хаос", my_p.chaos, fr_p.chaos),
        ("Интеллект", my_p.intellect, fr_p.intellect),
        ("Энергия", my_p.energy, fr_p.energy),
        ("Креативность", my_p.creativity, fr_p.creativity),
    ]

    lines = ["👥 <b>СРАВНЕНИЕ С ДРУГОМ</b>\n"]
    for name, a, b in categories:
        winner = "ты" if a > b else ("друг" if b > a else "ничья")
        diff = abs(a - b)
        lines.append(f"{name}: {a} vs {b} — разница {diff} ({winner})")

    lines.append("\nБез негатива: оба — легенды 😎")
    await callback.message.answer("\n".join(lines))