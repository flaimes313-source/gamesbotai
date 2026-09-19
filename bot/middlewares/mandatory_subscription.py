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


PASS_THROUGH_COMMANDS = ("/start", "/help", "/cancel")
PASS_THROUGH_CALLBACKS = ("sub_check_",)


def _build_channel_url(campaign: SubscriptionCampaign) -> str:
    """Возвращает валидный https://t.me/... URL для кнопки."""
    url = campaign.channel_link
    if url and url.startswith("http"):
        return url
    if campaign.channel_username:
        username = campaign.channel_username.lstrip("@")
        return f"https://t.me/{username}"
    # Крайний фолбэк
    return "https://t.me/telegram"


def _build_gate_kb(campaign: SubscriptionCampaign) -> InlineKeyboardMarkup:
    url = _build_channel_url(campaign)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📢 Подписаться", url=url)],
            [InlineKeyboardButton(
                text="✅ Я подписался",
                callback_data=f"sub_check_{campaign.id}",
            )],
        ]
    )


def _build_gate_text(campaign: SubscriptionCampaign) -> str:
    url = _build_channel_url(campaign)
    return (
        "🔒 <b>Требуется подписка</b>\n\n"
        "Чтобы пользоваться ботом, подпишись на канал:\n"
        f"👉 {url}\n\n"
        "После подписки нажми «✅ Я подписался»."
    )


class MandatorySubscriptionMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        # --- Флаг ---
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

        # --- Пропуски ---
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

        # --- Pass-through ---
        if isinstance(event, Message):
            text = (event.text or "").strip()
            first = text.split()[0] if text else ""
            if first in PASS_THROUGH_COMMANDS:
                return await handler(event, data)

        if isinstance(event, CallbackQuery):
            data_str = event.data or ""
            if any(data_str.startswith(p) for p in PASS_THROUGH_CALLBACKS):
                return await handler(event, data)

        # --- Кампания ---
        campaign = None
        user_row = None
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
                    logger.info(f"[GATE] user {from_user.id} not in DB — pass through")
                    return await handler(event, data)

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

        # --- Живая проверка ---
        bot = data.get("bot")
        ok = False
        if bot is not None:
            try:
                ok = await is_subscribed(bot, from_user.id, campaign.channel_id)
            except Exception:
                logger.exception("[GATE] is_subscribed failed")
                ok = False

        if ok:
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

        # --- НЕ подписан → показать экран ---
        logger.info(f"[GATE] user={from_user.id} not subscribed — showing gate")
        await self._send_gate(event, campaign, from_user.id, bot)
        return None

    async def _send_gate(
        self,
        event: TelegramObject,
        campaign: SubscriptionCampaign,
        user_id: int,
        bot,
    ) -> None:
        kb = _build_gate_kb(campaign)
        text = _build_gate_text(campaign)

        sent = False
        err: Exception | None = None

        # 1. Отвечаем на callback (для всплывающего окна)
        if isinstance(event, CallbackQuery):
            try:
                await event.answer("❌ Сначала подпишись на канал", show_alert=True)
            except Exception as e:
                logger.warning(f"[GATE] callback.answer failed: {e}")

        # 2. Отправляем через bot.send_message напрямую — самый надёжный способ
        if bot is not None:
            # Определяем chat_id
            chat_id = None
            if isinstance(event, Message):
                chat_id = event.chat.id
            elif isinstance(event, CallbackQuery):
                chat_id = event.message.chat.id

            if chat_id is not None:
                try:
                    await bot.send_message(chat_id, text, reply_markup=kb)
                    sent = True
                    logger.info(f"[GATE] sent via bot.send_message to chat_id={chat_id}")
                except Exception as e:
                    err = e
                    logger.exception(f"[GATE] bot.send_message failed: {e}")

        # 3. Fallback: event.answer()
        if not sent:
            try:
                if isinstance(event, Message):
                    await event.answer(text, reply_markup=kb)
                    sent = True
                    logger.info(f"[GATE] sent via event.answer (Message)")
                elif isinstance(event, CallbackQuery):
                    await event.message.answer(text, reply_markup=kb)
                    sent = True
                    logger.info(f"[GATE] sent via event.message.answer (Callback)")
            except Exception as e:
                err = e
                logger.exception(f"[GATE] fallback send failed: {e}")

        # 4. Если всё равно не отправилось — логируем явно
        if not sent:
            logger.error(
                f"[GATE] FAILED to deliver subscription gate to user {user_id}. "
                f"Last error: {err}"
            )

        try:
            await track(
                "subscription_gate_shown",
                telegram_id=user_id,
                payload={"campaign_id": campaign.id, "sent": sent},
            )
        except Exception:
            pass