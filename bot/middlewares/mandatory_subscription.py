from datetime import datetime, timezone
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


# Что пропускаем, даже если юзер не подписан
WHITELIST_CALLBACKS = ("sub_check_",)
WHITELIST_COMMANDS = ("/help", "/cancel")


class MandatorySubscriptionMiddleware(BaseMiddleware):
    """
    Hard gate: пока пользователь не подпишется на активный канал,
    бот ничего не отвечает, кроме экрана подписки.

    Пропускаются:
    - Админы
    - Whitelist
    - PRO-подписчики
    - Callback-и проверки подписки (sub_check_*)
    - Команды /help, /cancel
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        # Флаг обязательных подписок
        if not await is_enabled("mandatory_subscriptions_enabled", default=False):
            return await handler(event, data)

        from_user = data.get("event_from_user")
        if from_user is None:
            return await handler(event, data)

        # --- Пропуски без проверки ---

        # 1. Админы
        if from_user.id in config.ADMIN_IDS:
            return await handler(event, data)

        # 2. Whitelist
        if await is_whitelisted(from_user.id):
            return await handler(event, data)

        # 3. PRO-подписчики
        if await is_premium(from_user.id):
            return await handler(event, data)

        # 4. Whitelist callback-и (проверка подписки)
        if isinstance(event, CallbackQuery):
            data_str = event.data or ""
            if any(data_str.startswith(p) for p in WHITELIST_CALLBACKS):
                return await handler(event, data)

        # 5. Whitelist команды
        if isinstance(event, Message):
            text = (event.text or "").strip()
            first = text.split()[0] if text else ""
            if first in WHITELIST_COMMANDS:
                return await handler(event, data)

        # --- Проверяем активную кампанию ---
        async with async_session() as session:
            campaign = (await session.execute(
                select(SubscriptionCampaign)
                .where(SubscriptionCampaign.is_active.is_(True))
                .where(SubscriptionCampaign.channel_id.isnot(None))
                .limit(1)
            )).scalar_one_or_none()

            if campaign is None:
                # Нет активной кампании — пропускаем всё
                return await handler(event, data)

            # Уже подтверждена?
            user_row = (await session.execute(
                select(User).where(User.telegram_id == from_user.id)
            )).scalar_one_or_none()

            if user_row is not None:
                existing = (await session.execute(
                    select(SubscriptionEvent)
                    .where(SubscriptionEvent.campaign_id == campaign.id)
                    .where(SubscriptionEvent.user_id == user_row.id)
                    .where(SubscriptionEvent.status == "confirmed")
                )).scalar_one_or_none()

                if existing:
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
            # Сохраняем подтверждение и пропускаем
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

        # --- НЕ подписан — блокируем ---

        # Отвечаем на callback, чтобы не зависало
        if isinstance(event, CallbackQuery):
            try:
                await event.answer("❌ Сначала подпишись на канал", show_alert=True)
            except Exception:
                pass

        channel_url = campaign.channel_link or (
            f"https://t.me/{campaign.channel_username}"
            if campaign.channel_username
            else "https://t.me/"
        )

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
            "🔒 <b>Доступ к боту закрыт</b>\n\n"
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
            telegram_id=from_user.id,
            payload={"campaign_id": campaign.id},
        )

        # Не пропускаем апдейт дальше
        return None