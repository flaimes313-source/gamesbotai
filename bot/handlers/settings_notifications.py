"""
UI настроек уведомлений (Этап 1 + Этап 4).

Доступ:
    ⚙️ Настройки → 🔔 Уведомления

Показывает 8 тумблеров категорий (вкл/выкл).

Callbacks:
- notif_menu — открыть меню.
- notif_toggle_<name> — переключить тумблер.
- settings — вернуться в настройки.
"""

from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy import select

from database.connection import async_session
from database.models import User
from services.analytics.tracker import track
from services.notifications.hub import (
    get_notification_settings,
    notifications_menu_kb,
    update_notification_setting,
)
from utils.logging import get_logger

router = Router()
logger = get_logger(__name__)


# ============================================================
# ТЕКСТ ЭКРАНА
# ============================================================
_NOTIF_TEXT = (
    "🔔 <b>УВЕДОМЛЕНИЯ</b>\n\n"
    "Выбери, что присылать. Нажми, чтобы включить или выключить.\n\n"
    "✅ — включено\n"
    "❌ — выключено\n\n"
    "<i>Мы не шлём больше 2 уведомлений в день "
    "и не беспокоим ночью (23:00–08:00).</i>\n\n"
    "Настрой то, что тебе важно."
)


# ============================================================
# МАППИНГ: короткое имя → поле в UserNotificationSettings
# ============================================================
_NAME_TO_FIELD = {
    "daily_result": "daily_result_enabled",
    "horoscope": "horoscope_enabled",
    "secret_feature": "secret_feature_enabled",
    "profile_views": "profile_views_enabled",
    "weekly_vibe": "weekly_vibe_enabled",
    "tops": "tops_enabled",
    "premium_reminder": "premium_reminder_enabled",
    "chat_reminder": "chat_reminder_enabled",
}


# ============================================================
# ОТКРЫТИЕ МЕНЮ
# ============================================================
@router.callback_query(F.data == "notif_menu")
async def cb_notif_menu(callback: CallbackQuery):
    await callback.answer()

    # Ищем юзера
    async with async_session() as session:
        user = (await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )).scalar_one_or_none()

    if user is None:
        await callback.message.answer("Сначала отправь фото — появятся настройки.")
        return

    settings = await get_notification_settings(user.id)

    try:
        await callback.message.edit_text(
            _NOTIF_TEXT,
            reply_markup=notifications_menu_kb(settings),
        )
    except Exception:
        # Если сообщение — фото (карточка), edit_text упадёт. Тогда answer.
        await callback.message.answer(
            _NOTIF_TEXT,
            reply_markup=notifications_menu_kb(settings),
        )

    try:
        await track("notif_menu_viewed", telegram_id=callback.from_user.id)
    except Exception:
        logger.exception("[NOTIF] track failed")


# ============================================================
# ПЕРЕКЛЮЧЕНИЕ ТУМБЛЕРА
# ============================================================
@router.callback_query(F.data.startswith("notif_toggle_"))
async def cb_notif_toggle(callback: CallbackQuery):
    # notif_toggle_horoscope → horoscope
    name = callback.data.replace("notif_toggle_", "").strip()

    field = _NAME_TO_FIELD.get(name)
    if not field:
        await callback.answer("Неизвестная категория", show_alert=True)
        return

    # Ищем юзера
    async with async_session() as session:
        user = (await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )).scalar_one_or_none()

    if user is None:
        await callback.answer("Сначала отправь фото", show_alert=True)
        return

    # Читаем текущее значение
    settings = await get_notification_settings(user.id)
    current = settings.get(field, True)
    new_value = not current

    # Обновляем
    ok = await update_notification_setting(user.id, field, new_value)
    if not ok:
        await callback.answer("Не удалось сохранить", show_alert=True)
        return

    await callback.answer("Сохранено ✅" if new_value else "Отключено ❌")

    # Обновляем клавиатуру
    fresh = await get_notification_settings(user.id)
    try:
        await callback.message.edit_reply_markup(
            reply_markup=notifications_menu_kb(fresh)
        )
    except Exception:
        try:
            await callback.message.answer(
                _NOTIF_TEXT,
                reply_markup=notifications_menu_kb(fresh),
            )
        except Exception:
            logger.exception("[NOTIF] update keyboard failed")

    try:
        await track(
            "notif_toggle",
            telegram_id=callback.from_user.id,
            payload={"field": field, "value": new_value},
        )
    except Exception:
        logger.exception("[NOTIF] track failed")