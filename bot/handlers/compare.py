from aiogram import F, Router
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select

from database.connection import async_session
from database.models import Profile, User
from utils.logging import get_logger

router = Router()
logger = get_logger(__name__)


async def _send_comparison(message_or_callback, telegram_id: int) -> None:
    """
    Сравнивает пользователя с его рефералом (другом, пришедшим по ссылке).
    """
    async with async_session() as session:
        user = (await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )).scalar_one_or_none()

        if user is None:
            text = "Сначала отправь фото — создай свой профиль!"
        elif user.referrer_id is None:
            text = (
                "👥 <b>Сравнить с другом</b>\n\n"
                "Пока сравнить не с кем.\n\n"
                "Поделись своей ссылкой с другом — когда он зайдёт по ней "
                "и пройдёт свой анализ, вы сможете сравнить результаты!"
            )
        else:
            referrer = (await session.execute(
                select(User).where(User.id == user.referrer_id)
            )).scalar_one_or_none()

            if referrer is None:
                text = "Не удалось найти друга 😔"
            else:
                my_p = (await session.execute(
                    select(Profile).where(Profile.user_id == user.id)
                    .order_by(Profile.id.desc()).limit(1)
                )).scalar_one_or_none()

                fr_p = (await session.execute(
                    select(Profile).where(Profile.user_id == referrer.id)
                    .order_by(Profile.id.desc()).limit(1)
                )).scalar_one_or_none()

                if not my_p or not fr_p:
                    text = "У кого-то из вас пока нет профиля. Пусть оба отправят фото!"
                else:
                    text = _format_comparison(my_p, fr_p)

    # Отправляем
    if isinstance(message_or_callback, CallbackQuery):
        await message_or_callback.message.answer(text)
    else:
        await message_or_callback.answer(text)


def _format_comparison(my_p: Profile, fr_p: Profile) -> str:
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
        if a > b:
            winner = "ты"
        elif b > a:
            winner = "друг"
        else:
            winner = "ничья"
        diff = abs(a - b)
        lines.append(f"{name}: <b>{a}</b> vs <b>{b}</b> — разница {diff} ({winner})")

    lines.append("\nБез негатива: оба — легенды 😎")
    return "\n".join(lines)


# ============================================================
# REPLY-КНОПКА «👥 Сравнить»
# ============================================================
@router.message(F.text == "👥 Сравнить")
async def compare_from_menu(message: Message):
    await _send_comparison(message, message.from_user.id)


# ============================================================
# CALLBACK из профиля / других меню
# ============================================================
@router.callback_query(F.data == "compare_menu")
async def compare_from_callback(callback: CallbackQuery):
    await callback.answer()
    await _send_comparison(callback, callback.from_user.id)