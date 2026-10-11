"""
Удаление всех данных юзера (152-ФЗ).

Доступ: ⚙️ Настройки → 🗑 Удалить данные.
Подтверждение → удаление → пересылка обновлённой клавиатуры.
"""

from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy import select

from bot.keyboards.main import delete_data_confirm_kb, main_menu_kb
from database.connection import async_session
from database.models import User
from services.analytics.tracker import track
from services.premium import is_premium
from utils.logging import get_logger

router = Router()
logger = get_logger(__name__)


_CONFIRM_TEXT = (
    "🗑 <b>УДАЛИТЬ ВСЕ ДАННЫЕ?</b>\n\n"
    "Это <b>необратимо</b>. Будет удалено:\n\n"
    "• Все анализы фото\n"
    "• Твой профиль\n"
    "• История AI-друга\n"
    "• Тесты и достижения\n"
    "• Чаты, матчи, сообщения\n"
    "• Очки, стрики, коллекция архетипов\n"
    "• PRO (если была активна)\n\n"
    "❗ Отменить нельзя.\n\n"
    "<i>Сам аккаунт бота останется — сможешь начать заново.</i>\n\n"
    "Точно удалить всё?"
)


@router.callback_query(F.data == "delete_data_menu")
async def cb_delete_menu(callback: CallbackQuery):
    await callback.answer()
    try:
        await callback.message.edit_text(
            _CONFIRM_TEXT,
            reply_markup=delete_data_confirm_kb(),
        )
    except Exception:
        await callback.message.answer(
            _CONFIRM_TEXT,
            reply_markup=delete_data_confirm_kb(),
        )


@router.callback_query(F.data == "delete_data_yes")
async def cb_delete_yes(callback: CallbackQuery):
    await callback.answer("Удаляю…")

    telegram_id = callback.from_user.id

    async with async_session() as session:
        user = (await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )).scalar_one_or_none()

    if user is None:
        await callback.message.answer("Сначала отправь фото.")
        return

    user_id = user.id

    try:
        from services.account.delete_data import delete_all_user_data
        result = await delete_all_user_data(user_id)
    except Exception:
        logger.exception("[DELETE_DATA] failed")
        await callback.message.answer(
            "😔 Не удалось удалить данные. Попробуй позже или напиши в поддержку."
        )
        return

    try:
        await track(
            "account_data_deleted",
            telegram_id=telegram_id,
            payload={
                "profiles": result.get("profiles", 0),
                "analyses": result.get("analyses", 0),
                "messages": result.get("messages", 0),
                "ai_friend": result.get("ai_friend", 0),
            },
        )
    except Exception:
        pass

    is_pro = False
    try:
        is_pro = await is_premium(telegram_id)
    except Exception:
        pass

    await callback.message.answer(
        "✅ <b>Все данные удалены.</b>\n\n"
        f"Удалено анализов: <b>{result.get('analyses', 0)}</b>\n"
        f"Удалено сообщений AI-другу: <b>{result.get('ai_friend', 0)}</b>\n\n"
        "Ты можешь начать заново — просто отправь фото 📸",
        reply_markup=main_menu_kb(is_pro=is_pro),
    )


@router.callback_query(F.data == "delete_data_no")
async def cb_delete_no(callback: CallbackQuery):
    await callback.answer("Отменено")
    try:
        await callback.message.edit_text("👍 Ок, ничего не удаляю.")
    except Exception:
        await callback.message.answer("👍 Ок, ничего не удаляю.")

    try:
        await track("account_delete_cancelled", telegram_id=callback.from_user.id)
    except Exception:
        pass