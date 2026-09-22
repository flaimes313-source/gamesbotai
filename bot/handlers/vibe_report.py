"""
Хендлер кнопки «🧠 Мой вайб-отчёт» (Шаг 1.3).

Доступен из меню «👤 Мой профиль» → кнопка «🧠 Мой вайб-отчёт».
Требует >= MIN_ANALYSES_FOR_REPORT (3) анализов у юзера.

Возвращает:
- либо AI-текст отчёта (HTML) + inline-кнопки,
- либо заглушку «Сделай ещё N анализов».
"""

from aiogram import F, Router
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from sqlalchemy import select

from database.connection import async_session
from database.models import User
from services.analytics.tracker import track
from services.analysis.vibe_report import (
    MIN_ANALYSES_FOR_REPORT,
    build_vibe_report,
)
from utils.logging import get_logger

router = Router()
logger = get_logger(__name__)


# ============================================================
# Клавиатура после отчёта
# ============================================================
def _report_kb() -> InlineKeyboardMarkup:
    """
    Кнопки под текстом отчёта:
    - «Обновить» → перегенерит отчёт (callback тот же).
    - «Поделиться» → общая логика шара (share_profile).
    - «В профиль» → назад.
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="🔄 Обновить отчёт",
                callback_data="vibe_report",
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


# ============================================================
# Хендлер
# ============================================================
@router.callback_query(F.data == "vibe_report")
async def cb_vibe_report(callback: CallbackQuery):
    await callback.answer("Готовлю отчёт…")

    # Ищем юзера
    async with async_session() as session:
        user = (await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )).scalar_one_or_none()

    if user is None:
        await callback.message.answer(
            "Сначала отправь фото, чтобы я узнал твой вайб!"
        )
        return

    # Генерим отчёт
    try:
        report = await build_vibe_report(user.id, weekly=False)
    except Exception:
        logger.exception("[VIBE] handler build_vibe_report failed")
        await callback.message.answer(
            "😔 Не удалось собрать отчёт. Попробуй позже."
        )
        return

    # Мало анализов — заглушка
    if not report.get("available"):
        have = report.get("have", 0)
        need = report.get("need", MIN_ANALYSES_FOR_REPORT)
        left = max(0, need - have)
        await callback.message.answer(
            "🧠 <b>Мой вайб-отчёт</b>\n\n"
            f"Отчёт откроется после <b>{need}</b> анализов.\n"
            f"У тебя сейчас: <b>{have}</b>.\n\n"
            f"Осталось сделать: <b>{left}</b> 📸\n\n"
            "<i>Чем больше анализов — тем точнее отчёт.</i>"
        )
        return

    # Собираем финальный текст
    text = report.get("text", "").strip()
    recommendation = report.get("recommendation", "").strip()

    # Обрезаем, если AI разошёлся больше 4000 символов (лимит Telegram)
    if len(text) > 3800:
        text = text[:3800] + "…"

    # Приписка с рекомендацией (если есть)
    if recommendation:
        text += f"\n\n💡 <b>Совет:</b> {recommendation}"

    # Заголовок
    header = "🧠 <b>МОЙ ВАЙБ-ОТЧЁТ</b>\n\n"

    try:
        await callback.message.answer(
            header + text,
            reply_markup=_report_kb(),
        )
    except Exception:
        logger.exception("[VIBE] send failed")
        await callback.message.answer(
            "😔 Не удалось отправить отчёт. Попробуй ещё раз."
        )
        return

    # Аналитика
    try:
        await track(
            "vibe_report_viewed",
            telegram_id=callback.from_user.id,
            payload={
                "weekly": False,
                "text_len": len(text),
                "has_recommendation": bool(recommendation),
            },
        )
    except Exception:
        logger.exception("[VIBE] track failed")