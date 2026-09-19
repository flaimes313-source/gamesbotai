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


# Что НЕ блокируем — эти команды и кнопки всегда проходят
PASS_THROUGH_COMMANDS = ("/start", "/help", "/cancel")
PASS_THROUGH_CALLBACKS = ("sub_check_",)


def _get_first_word(text: str) -> str:
    text = (text or "").strip()
    if not text:
        return ""
    return text.split()[0]


def _build_gate_kb(campaign: SubscriptionCampaign) -> InlineKeyboardMarkup:
    channel_url = campaign.channel_link
    if not channel_url and campaign.channel_username:
        channel_url = f"https://t.me/{campaign.channel_username}"
    if not channel_url:
        channel_url = "https://t.me/telegram"

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📢 Подписаться", url=channel_url)],
            [InlineKeyboardButton(
                text="✅ Я подписался",
                callback_data=f"sub_check_{campaign.id}",
            )],
        ]
    )


def _build_gate_text(campaign: SubscriptionCampaign) -> str:
    channel_url = campaign.channel_link
    if not channel_url and campaign.channel_username:
        channel_url = f"https://t.me/{campaign.channel_username}"
    if not channel_url:
        channel_url = "https://t.me/telegram"

    return (
        "🔒 <b>Требуется подписка</b>\n\n"
        "Чтобы пользоваться ботом, подпишись на канал:\n"
        f"👉 {channel_url}\n\n"
        "После подписки нажми «✅ Я подписался»."
    )


class MandatorySubscriptionMiddleware(BaseMiddleware):
    """
    Логика:

    1. /start, /help, /cancel, sub_check_* — пропускаем всегда.
    2. Админ / whitelist / PRO — пропускаем всегда.
    3. Если есть активная кампания и юзер не подписан —
       ЛЮБОЕ действие блокируется экраном подписки.
    4. После подписки (is_subscribed → True) — пропускаем.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        # --- 0. Флаг ---
        try:
            flag_on = await is_enabled("mandatory_subscriptions_enabled", default=False)
        except Exception:
            logger.exception("[GATE] is_enabled failed")
            flag_on = False

        if not flag_on:
            return await handler(event, data)

        from_user = data.get("event_from_user")
        if from_user is None:
            return await handler(event, data)

        # --- 1. Пропуски ---
        if from_user.id in config.ADMIN_IDS:
            return await handler(event, data)

        try:
            if await is_whitelisted(from_user.id):
                return await handler(event, data)
        except Exception:
            logger.exception("[GATE] whitelist check failed")

        try:
            if await is_premium(from_user.id):
                return await handler(event, data)
        except Exception:
            logger.exception("[GATE] premium check failed")

        # --- 2. Pass-through команды ---
        if isinstance(event, Message):
            first = _get_first_word(event.text or "")
            if first in PASS_THROUGH_COMMANDS:
                return await handler(event, data)

        if isinstance(event, CallbackQuery):
            data_str = event.data or ""
            if any(data_str.startswith(p) for p in PASS_THROUGH_CALLBACKS):
                return await handler(event, data)

        # --- 3. Активная кампания ---
        try:
            async with async_session() as session:
                campaign = (await session.execute(
                    select(SubscriptionCampaign)
                    .where(SubscriptionCampaign.is_active.is_(True))
                    .where(SubscriptionCampaign.channel_id.isnot(None))
                    .limit(1)
                )).scalar_one_or_none()

                if campaign is None:
                    logger.info("[GATE] no active campaign — pass through")
                    return await handler(event, data)

                user_row = (await session.execute(
                    select(User).where(User.telegram_id == from_user.id)
                )).scalar_one_or_none()

                if user_row is None:
                    # Юзера ещё нет в БД — пусть /start создаст
                    logger.info(f"[GATE] user {from_user.id} not in DB — pass through")
                    return await handler(event, data)

                # Уже подтверждено?
                existing = (await session.execute(
                    select(SubscriptionEvent)
                    .where(SubscriptionEvent.campaign_id == campaign.id)
                    .where(SubscriptionEvent.user_id == user_row.id)
                    .where(SubscriptionEvent.status == "confirmed")
                )).scalar_one_or_none()

                if existing:
                    logger.info(f"[GATE] user {from_user.id} already confirmed")
                    return await handler(event, data)
        except Exception:
            logger.exception("[GATE] campaign check failed")
            return await handler(event, data)

        # --- 4. Живая проверка через Telegram ---
        bot = data.get("bot")
        ok = False
        if bot is not None:
            try:
                ok = await is_subscribed(bot, from_user.id, campaign.channel_id)
            except Exception:
                logger.exception("[GATE] is_subscribed failed")
                ok = False

        if ok:
            # Сохраняем подтверждение и пропускаем
            try:
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
            except Exception:
                logger.exception("[GATE] failed to save confirmation")

            try:
                await track(
                    "subscription_confirmed",
                    telegram_id=from_user.id,
                    payload={"campaign_id": campaign.id, "source": "middleware"},
                )
            except Exception:
                pass

            return await handler(event, data)

        # --- 5. НЕ подписан → показываем экран подписки ---
        logger.info(f"[GATE] user={from_user.id} not subscribed — showing gate")
        await self._send_gate(event, campaign, from_user.id)
        return None

    # --------------------------------------------------------
    # Отправка экрана подписки
    # --------------------------------------------------------
    async def _send_gate(
        self,
        event: TelegramObject,
        campaign: SubscriptionCampaign,
        user_id: int,
    ) -> None:
        kb = _build_gate_kb(campaign)
        text = _build_gate_text(campaign)

        sent = False

        # Callback → show_alert + сообщение
        if isinstance(event, CallbackQuery):
            try:
                await event.answer("❌ Сначала подпишись на канал", show_alert=True)
            except Exception as e:
                logger.warning(f"[GATE] callback.answer failed: {e}")

            try:
                await event.message.answer(text, reply_markup=kb)
                sent = True
                logger.info(f"[GATE] sent to callback message for {user_id}")
            except Exception as e:
                logger.exception(f"[GATE] callback send failed: {e}")

        # Message → сообщение в тот же чат
        elif isinstance(event, Message):
            try:
                await event.answer(text, reply_markup=kb)
                sent = True
                logger.info(f"[GATE] sent to message chat for {user_id}")
            except Exception as e:
                logger.exception(f"[GATE] message send failed: {e}")

        # Fallback: отправка через bot напрямую
        if not sent:
            logger.warning(f"[GATE] primary send failed, fallback for {user_id}")

        try:
            await track(
                "subscription_gate_shown",
                telegram_id=user_id,
                payload={"campaign_id": campaign.id, "sent": sent},
            )
        except Exception:
            pass