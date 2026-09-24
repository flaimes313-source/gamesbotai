"""
Хендлер «Совместимость со звёздами» (Этап 3).

Кнопка в профиле → AI сравнивает вайб юзера с 20 персонажами
→ топ-3 с процентами.
"""

from aiogram import F, Router
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from sqlalchemy import select

from database.connection import async_session
from database.models import Profile, User
from services.analytics.tracker import track
from services.social.compatibility import (
    format_compatibility_message,
    get_compatibility,
)
from utils.logging import get_logger

router = Router()
logger = get_logger(__name__)


def _result_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="🔄 Ещё раз",
                callback_data="compat_run",
            )],
            [InlineKeyboardButton(
                text="📤 Поделиться",
                callback_data="share_profile",
            )],
            [InlineKeyboardButton(
                text="⬅️ В профиль",
                callback_data="my_profile",
            )],
        ]
    )


async def _keep_typing(bot, chat_id: int):
    """Держит «печатает…» пока AI думает."""
    import asyncio
    try:
        while True:
            try:
                await bot.send_chat_action(chat_id=chat_id, action="typing")
            except Exception:
                pass
            await asyncio.sleep(4)
    except asyncio.CancelledError:
        pass


@router.callback_query(F.data == "compat_run")
async def cb_compat_run(callback: CallbackQuery):
    await callback.answer("Считаю совместимость…")

    chat_id = callback.message.chat.id

    # Ищем юзера
    async with async_session() as session:
        user = (await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )).scalar_one_or_none()

    if user is None:
        await callback.message.answer("Сначала отправь фото — нужен профиль!")
        return

    # Проверяем, есть ли профиль
    async with async_session() as session:
        profile = (await session.execute(
            select(Profile)
            .where(Profile.user_id == user.id)
            .order_by(Profile.id.desc())
            .limit(1)
        )).scalar_one_or_none()

    if profile is None:
        await callback.message.answer(
            "📸 Сначала сделай анализ фото — тогда сравню тебя со звёздами!"
        )
        return

    # Запускаем «печатает…»
    import asyncio
    typing_task = asyncio.create_task(_keep_typing(callback.bot, chat_id))

    try:
        results = await get_compatibility(user.id)
    except Exception:
        logger.exception("[COMPAT] handler failed")
        typing_task.cancel()
        await callback.message.answer(
            "😔 Не удалось посчитать. Попробуй позже."
        )
        return
    finally:
        typing_task.cancel()

    if not results:
        await callback.message.answer(
            "😔 Не получилось определить совместимость. Попробуй ещё раз чуть позже."
        )
        return

    text = format_compatibility_message(results)

    try:
        await callback.message.answer(text, reply_markup=_result_kb())
    except Exception:
        logger.exception("[COMPAT] send failed")
        await callback.message.answer("😔 Не удалось отправить. Попробуй ещё раз.")
        return

    try:
        await track(
            "compat_viewed",
            telegram_id=callback.from_user.id,
            payload={"top": [r["code"] for r in results]},
        )
    except Exception:
        logger.exception("[COMPAT] track failed")