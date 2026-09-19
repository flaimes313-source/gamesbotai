from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    TelegramObject,
)
from sqlalchemy import select

from config import config
from database.connection import async_session
from database.models import SubscriptionCampaign, SubscriptionEvent, User
from services.analytics.tracker import track
from services.feature_flags import is_enabled
from services.premium import is_premium
from services.subscriptions.checker import is_subscribed
from services.whitelist import is_whitelisted
from utils.logging import get_logger

logger = get_logger(__name__)


# Что пропускаем ВСЕГДА (не блокируем) — показываем меню, приветствие
PASS_THROUGH_COMMANDS = ("/start", "/help", "/cancel")

# Callback-и, которые не блокируем (кнопка проверки подписки)
PASS_THROUGH_CALLBACKS = ("sub_check_",)

# Раз в сколько дней напоминать подписанным (мягкий оффер)
REMINDER_DAYS = 7


class MandatorySubscriptionMiddleware(BaseMiddleware):
    """
    Логика:

    1. /start, /help, /cancel — пропускаем ВСЕГДА (показываем меню).
    2. Первое ДЕЙСТВИЕ (фото, кнопки меню) — проверка подписки.
    3. Если не подписан → блок + экран подписки.
    4. Если подписан → пропускаем и запоминаем.
    5. Раз в 7 дней — мягкий оффер (не блокирующий).
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        # Флаг выключен — пропускаем всё
        if not await is_enabled("mandatory_subscriptions_enabled", default=False):
            return await handler(event, data)

        from_user = data.get("event_from_user")
        if from_user is None:
            return await handler(event, data)

        # Пропускаем админов, whitelist и PRO
        if from_user.id in config.ADMIN_IDS:
            return await handler(event, data)
        if await is_whitelisted(from_user.id):
            return await handler(event, data)
        if await is_premium(from_user.id):
            return await handler(event, data)

        # --- Пропускаем /start, /help, /cancel и sub_check_ ---
        if isinstance(event, Message):
            text = (event.text or "").strip()
            first = text.split()[0] if text else ""
            if first in PASS_THROUGH_COMMANDS:
                return await handler(event, data)

        if isinstance(event, CallbackQuery):
            data_str = event.data or ""
            if any(data_str.startswith(p) for p in PASS_THROUGH_CALLBACKS):
                return await handler(event, data)

        # --- Активная кампания ---
        async with async_session() as session:
            campaign = (await session.execute(
                select(SubscriptionCampaign)
                .where(SubscriptionCampaign.is_active.is_(True))
                .where(SubscriptionCampaign.channel_id.isnot(None))
                .limit(1)
            )).scalar_one_or_none()

            # Нет кампании — пропускаем
            if campaign is None:
                return await handler(event, data)

            user_row = (await session.execute(
                select(User).where(User.telegram_id == from_user.id)
            )).scalar_one_or_none()

            # Юзер ещё не создан (первый /start ещё не дошёл до БД)
            if user_row is None:
                # Пропускаем — пусть сначала /start создаст запись
                return await handler(event, data)

            # Уже подтверждена подписка?
            existing = (await session.execute(
                select(SubscriptionEvent)
                .where(SubscriptionEvent.campaign_id == campaign.id)
                .where(SubscriptionEvent.user_id == user_row.id)
                .where(SubscriptionEvent.status == "confirmed")
            )).scalar_one_or_none()

            if existing:
                # --- Мягкое напоминание раз в 7 дней (не блокирует) ---
                if (
                    existing.confirmed_at
                    and (datetime.now(timezone.utc) - existing.confirmed_at) > timedelta(days=REMINDER_DAYS)
                ):
                    # Обновляем дату подтверждения (чтобы не напоминать каждый раз)
                    existing.confirmed_at = datetime.now(timezone.utc)
                    await session.commit()
                    # Отправляем мягкое напоминание асинхронно — не блокируем
                    try:
                        await _send_soft_reminder(event, campaign)
                    except Exception:
                        logger.exception("Soft reminder failed")

                return await handler(event, data)

        # --- Живая проверка через Telegram API ---
        bot = data.get("bot")
        ok = False
        if bot is not None:
            try:
                ok = await is_subscribed(bot, from_user.id, campaign.channel_id)
            except Exception:
                ok = False

        if ok:
            # Сохраняем подтверждение
            async with async_session() as session:
                user_row = (await session.execute(
                    select(User).where(User.telegram_id == from_user.id)
                )).scalar_one_or_none()

                if user_row:
                    now = datetime.now(timezone.utc)
                    session.add(SubscriptionEvent(
                        campaign_id=campaign.id,
                        user_id=user_row.id,
                        channel_id=campaign.channel_id,
                        status="confirmed",
                        checked_at=now,
                        confirmed_at=now,
                    ))
                    await session.commit()

            await track(
                "subscription_confirmed",
                telegram_id=from_user.id,
                payload={"campaign_id": campaign.id, "source": "middleware"},
            )
            return await handler(event, data)

        # --- НЕ подписан — БЛОКИРУЕМ ---
        await _send_gate(event, campaign, from_user.id)
        return None


# ============================================================
# Отправка экрана подписки
# ============================================================
async def _send_gate(event: TelegramObject, campaign: SubscriptionCampaign, user_id: int) -> None:
    if isinstance(event, CallbackQuery):
        try:
            await event.answer("❌ Сначала подпишись на канал", show_alert=True)
        except Exception:
            pass

    channel_url = campaign.channel_link or (
        f"https://t.me/{campaign.channel_username}" if campaign.channel_username else None
    )
    if not channel_url or channel_url == "https://t.me/":
        channel_url = f"https://t.me/{campaign.channel_username or 'telegram'}"

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📢 Подписаться", url=channel_url)],
            [InlineKeyboardButton(
                text="✅ Я подписался",
                callback_data=f"sub_check_{campaign.id}",
            )],
        ]
    )

    text = (
        "🔒 <b>Требуется подписка</b>\n\n"
        "Чтобы пользоваться ботом, подпишись на канал:\n"
        f"👉 {channel_url}\n\n"
        "После подписки нажми «✅ Я подписался»."
    )

    try:
        if isinstance(event, Message):
            await event.answer(text, reply_markup=kb)
        elif isinstance(event, CallbackQuery):
            await event.message.answer(text, reply_markup=kb)
    except Exception:
        logger.exception("Failed to send subscription gate")

    await track(
        "subscription_gate_shown",
        telegram_id=user_id,
        payload={"campaign_id": campaign.id},
    )


# ============================================================
# Мягкое напоминание (не блокирует)
# ============================================================
async def _send_soft_reminder(event: TelegramObject, campaign: SubscriptionCampaign) -> None:
    """
    Отправляет мягкое напоминание подписанному юзеру.
    НЕ блокирует действие — просто уведомление.
    """
    channel_url = campaign.channel_link or (
        f"https://t.me/{campaign.channel_username}" if campaign.channel_username else None
    )
    if not channel_url:
        return

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📢 Перейти в канал", url=channel_url)],
        ]
    )

    text = (
        "💡 <b>Напоминание</b>\n\n"
        "Спасибо, что пользуешься ботом!\n"
        f"Поддержи канал-партнёр: {channel_url}"
    )

    try:
        if isinstance(event, Message):
            await event.answer(text, reply_markup=kb)
        elif isinstance(event, CallbackQuery):
            await event.message.answer(text, reply_markup=kb)
    except Exception:
        logger.exception("Soft reminder send failed")