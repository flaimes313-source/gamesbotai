"""
Vibe-профиль (Этап G) — единый экран со сводкой о юзере.

Доступ: 👤 Мой профиль → 🎨 Vibe-профиль.
"""

from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy import select

from bot.keyboards.main import vibe_profile_kb
from database.connection import async_session
from database.models import User
from services.analytics.tracker import track
from services.premium import is_premium
from utils.logging import get_logger

router = Router()
logger = get_logger(__name__)


@router.callback_query(F.data == "vibe_profile")
async def cb_vibe_profile(callback: CallbackQuery):
    await callback.answer("Собираю твой вайб…")

    async with async_session() as session:
        user = (await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )).scalar_one_or_none()

    if user is None:
        await callback.message.answer(
            "Сначала отправь фото — я должен знать твой вайб!"
        )
        return

    try:
        from services.analysis.vibe_profile import (
            build_vibe_profile,
            format_vibe_profile,
        )
        data = await build_vibe_profile(user.id)
    except Exception:
        logger.exception("[VIBE_PROFILE] build failed")
        await callback.message.answer("😔 Не удалось собрать профиль. Попробуй позже.")
        return

    if data is None:
        await callback.message.answer(
            "У тебя пока нет профиля. Отправь фото 📸 чтобы начать!"
        )
        return

    text = format_vibe_profile(data)

    try:
        await callback.message.answer(text, reply_markup=vibe_profile_kb())
    except Exception:
        logger.exception("[VIBE_PROFILE] send failed")

    try:
        await track(
            "vibe_profile_viewed",
            telegram_id=callback.from_user.id,
            payload={
                "level": data.get("level", 1),
                "analyses": data.get("total_analyses", 0),
                "is_legendary": data.get("is_legendary", False),
                "collection": data.get("collection", {}).get("unique", 0),
            },
        )
    except Exception:
        logger.exception("[VIBE_PROFILE] track failed")