from typing import Optional

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select

from database.connection import async_session
from database.models import Profile, User
from services.feature_flags import is_enabled
from utils.logging import get_logger

router = Router()
logger = get_logger(__name__)


async def _latest_profile(session, user_id: int) -> Optional[Profile]:
    return (
        await session.execute(
            select(Profile)
            .where(Profile.user_id == user_id)
            .order_by(Profile.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


def _format_comparison(my_p: Profile, fr_p: Profile, friend_name: str = "Друг") -> str:
    categories = [
        ("Харизма", my_p.charisma, fr_p.charisma),
        ("Юмор", my_p.humor, fr_p.humor),
        ("Хаос", my_p.chaos, fr_p.chaos),
        ("Интеллект", my_p.intellect, fr_p.intellect),
        ("Энергия", my_p.energy, fr_p.energy),
        ("Креативность", my_p.creativity, fr_p.creativity),
    ]

    lines = [f"👥 <b>СРАВНЕНИЕ С {friend_name.upper()}</b>\n"]
    my_wins = 0
    friend_wins = 0

    for name, a, b in categories:
        if a > b:
            winner = "ты"
            my_wins += 1
        elif b > a:
            winner = "друг"
            friend_wins += 1
        else:
            winner = "ничья"
        diff = abs(a - b)
        lines.append(f"{name}: <b>{a}</b> vs <b>{b}</b> — разница {diff} ({winner})")

    lines.append("")
    if my_wins > friend_wins:
        lines.append(f"🏆 <b>Счёт: {my_wins}:{friend_wins} в твою пользу!</b>")
    elif friend_wins > my_wins:
        lines.append(f"🏆 <b>Счёт: {my_wins}:{friend_wins} в пользу друга.</b>")
    else:
        lines.append(f"🏆 <b>Счёт: {my_wins}:{friend_wins}. Ничья!</b>")

    lines.append("\nБез негатива: оба — легенды 😎")
    return "\n".join(lines)


async def _find_friend_for_comparison(session, me: User) -> Optional[User]:
    if me.referrer_id:
        friend = (
            await session.execute(
                select(User).where(User.id == me.referrer_id)
            )
        ).scalar_one_or_none()
        if friend:
            return friend

    return (
        await session.execute(
            select(User)
            .where(User.referrer_id == me.id)
            .order_by(User.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def _send_comparison(message_or_callback, telegram_id: int) -> None:
    if not await is_enabled("friend_comparison_enabled", default=True):
        text = "👥 Сравнение временно отключено."
        if isinstance(message_or_callback, CallbackQuery):
            await message_or_callback.message.answer(text)
        else:
            await message_or_callback.answer(text)
        return

    async with async_session() as session:
        me = (await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )).scalar_one_or_none()

        if me is None:
            text = "Сначала отправь фото — создай свой профиль!"
        else:
            friend = await _find_friend_for_comparison(session, me)

            if friend is None:
                text = (
                    "👥 <b>Сравнить с другом</b>\n\n"
                    "Пока сравнить не с кем.\n\n"
                    "📤 Поделись своей ссылкой с другом — когда он зайдёт по ней "
                    "и пройдёт свой анализ, вы сможете сравнить результаты!\n\n"
                    "Также можно сравнить себя с любым игроком из "
                    "«🎯 Найти игроков» — там есть кнопка «📊 Сравнить по цифрам»."
                )
            else:
                my_p = await _latest_profile(session, me.id)
                fr_p = await _latest_profile(session, friend.id)

                if not my_p or not fr_p:
                    text = (
                        "👥 <b>Сравнить с другом</b>\n\n"
                        "У кого-то из вас пока нет профиля.\n"
                        "Пусть оба отправят фото — и сравнение появится!"
                    )
                else:
                    friend_name = friend.first_name or "друг"
                    text = _format_comparison(my_p, fr_p, friend_name)

                    # Вовлечение: сравнение с другом
                    try:
                        from services.engagement.service import on_compare
                        await on_compare(me.id)
                    except Exception:
                        logger.exception("Engagement on_compare failed")

    if isinstance(message_or_callback, CallbackQuery):
        await message_or_callback.message.answer(text)
    else:
        await message_or_callback.answer(text)

    # Отправляем накопленные уведомления
    try:
        from services.engagement.notifications import flush_notifications
        if isinstance(message_or_callback, CallbackQuery):
            await flush_notifications(message_or_callback.bot, message_or_callback.from_user.id)
        else:
            await flush_notifications(message_or_callback.bot, message_or_callback.from_user.id)
    except Exception:
        logger.exception("flush_notifications failed")


@router.message(F.text == "👥 Сравнить")
async def compare_from_menu(message: Message):
    await _send_comparison(message, message.from_user.id)


@router.callback_query(F.data == "compare_menu")
async def compare_from_callback(callback: CallbackQuery):
    await callback.answer()
    await _send_comparison(callback, callback.from_user.id)


@router.callback_query(F.data.startswith("compare_with_"))
async def cb_compare_with(callback: CallbackQuery):
    await callback.answer("Сравниваю...")

    if not await is_enabled("friend_comparison_enabled", default=True):
        await callback.message.answer("👥 Сравнение временно отключено.")
        return

    target_id_str = callback.data.replace("compare_with_", "")
    try:
        target_user_id = int(target_id_str)
    except ValueError:
        await callback.message.answer("Некорректный игрок.")
        return

    async with async_session() as session:
        me = (await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )).scalar_one_or_none()

        if me is None:
            await callback.message.answer("Сначала отправь фото!")
            return

        target = (await session.execute(
            select(User).where(User.id == target_user_id)
        )).scalar_one_or_none()

        if target is None:
            await callback.message.answer("Игрок не найден.")
            return

        my_p = await _latest_profile(session, me.id)
        their_p = await _latest_profile(session, target.id)

        if not my_p:
            await callback.message.answer("У тебя пока нет профиля. Отправь фото!")
            return
        if not their_p:
            await callback.message.answer("У этого игрока пока нет профиля.")
            return

        target_name = target.first_name or "Игрок"
        text = _format_comparison(my_p, their_p, target_name)

    # Вовлечение: сравнение
    try:
        from services.engagement.service import on_compare
        await on_compare(me.id)
    except Exception:
        logger.exception("Engagement on_compare failed")

    await callback.message.answer(text)

    # Отправляем накопленные уведомления
    try:
        from services.engagement.notifications import flush_notifications
        await flush_notifications(callback.bot, callback.from_user.id)
    except Exception:
        logger.exception("flush_notifications failed")