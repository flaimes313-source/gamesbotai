from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List

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

MAX_CAMPAIGNS = 3


# ============================================================
# Утилиты
# ============================================================
def _build_channel_url(campaign: SubscriptionCampaign) -> str:
    url = campaign.channel_link
    if url and url.startswith("http"):
        return url
    if campaign.channel_username:
        username = campaign.channel_username.lstrip("@")
        return f"https://t.me/{username}"
    return "https://t.me/telegram"


def _build_multi_gate_kb(campaigns: List[SubscriptionCampaign]) -> InlineKeyboardMarkup:
    """Кнопки «Подписаться» для каждого канала + «Я подписался»."""
    rows = []
    for c in campaigns:
        url = _build_channel_url(c)
        label = c.name or c.channel_username or "Канал"
        # Обрезаем длинные названия
        if len(label) > 28:
            label = label[:26] + "…"
        rows.append([InlineKeyboardButton(text=f"📢 {label}", url=url)])

    # Кнопка «Я подписался» — общая (для всех кампаний)
    rows.append([InlineKeyboardButton(
        text="✅ Я подписался на все",
        callback_data="sub_check_all",
    )])

    return InlineKeyboardMarkup(inline_keyboard=rows)


def _build_multi_gate_text(campaigns: List[SubscriptionCampaign]) -> str:
    lines = [
        "🔒 <b>Требуется подписка</b>\n",
        f"Чтобы пользоваться ботом, подпишись на {len(campaigns)} канал(а):\n",
    ]
    for i, c in enumerate(campaigns, 1):
        url = _build_channel_url(c)
        label = c.name or c.channel_username or "Канал"
        lines.append(f"{i}. <b>{label}</b>\n   👉 {url}")

    lines.append("\nПосле подписки на все каналы нажми «✅ Я подписался на все».")
    return "\n".join(lines)


# ============================================================
# Middleware
# ============================================================
class MandatorySubscriptionMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
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

        # Пропуски
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

        # Pass-through
        if isinstance(event, Message):
            text = (event.text or "").strip()
            first = text.split()[0] if text else ""
            if first in PASS_THROUGH_COMMANDS:
                return await handler(event, data)

        if isinstance(event, CallbackQuery):
            data_str = event.data or ""
            if any(data_str.startswith(p) for p in PASS_THROUGH_CALLBACKS):
                return await handler(event, data)

        # --- Активные кампании (до 3) ---
        campaigns: List[SubscriptionCampaign] = []
        user_row = None
        try:
            async with async_session() as session:
                campaigns = list((await session.execute(
                    select(SubscriptionCampaign)
                    .where(SubscriptionCampaign.is_active.is_(True))
                    .where(SubscriptionCampaign.channel_id.isnot(None))
                    .order_by(SubscriptionCampaign.id.asc())
                    .limit(MAX_CAMPAIGNS)
                )).scalars().all())

                if not campaigns:
                    logger.info("[GATE] no active campaigns — pass through")
                    return await handler(event, data)

                user_row = (await session.execute(
                    select(User).where(User.telegram_id == from_user.id)
                )).scalar_one_or_none()

                if user_row is None:
                    logger.info(f"[GATE] user {from_user.id} not in DB — pass through")
                    return await handler(event, data)

                # Сколько кампаний уже подтверждено?
                confirmed_rows = (await session.execute(
                    select(SubscriptionEvent.campaign_id)
                    .where(SubscriptionEvent.user_id == user_row.id)
                    .where(SubscriptionEvent.status == "confirmed")
                    .where(SubscriptionEvent.campaign_id.in_([c.id for c in campaigns]))
                )).scalars().all()

                confirmed_ids = set(confirmed_rows)

                # Все подтверждены?
                if len(confirmed_ids) == len(campaigns):
                    return await handler(event, data)

                # Есть неподтверждённые кампании — продолжаем проверку
                unconfirmed = [c for c in campaigns if c.id not in confirmed_ids]

        except Exception:
            logger.exception("[GATE] campaign check failed")
            return await handler(event, data)

        # --- Живая проверка через Telegram API ---
        bot = data.get("bot")
        all_subscribed = True
        subscribed_ids: set = set()
        not_subscribed: List[SubscriptionCampaign] = []

        for c in unconfirmed:
            ok = False
            if bot is not None:
                try:
                    ok = await is_subscribed(bot, from_user.id, c.channel_id)
                except Exception:
                    logger.exception(f"[GATE] is_subscribed failed for {c.id}")
                    ok = False

            if ok:
                subscribed_ids.add(c.id)
            else:
                all_subscribed = False
                not_subscribed.append(c)

        # Сохраняем подтверждённые
        if subscribed_ids:
            try:
                async with async_session() as session:
                    user_row2 = (await session.execute(
                        select(User).where(User.telegram_id == from_user.id)
                    )).scalar_one_or_none()
                    if user_row2:
                        now = datetime.now(timezone.utc)
                        for cid in subscribed_ids:
                            # Проверяем, нет ли уже записи
                            existing = (await session.execute(
                                select(SubscriptionEvent)
                                .where(SubscriptionEvent.campaign_id == cid)
                                .where(SubscriptionEvent.user_id == user_row2.id)
                            )).scalar_one_or_none()
                            if existing:
                                existing.status = "confirmed"
                                existing.checked_at = now
                                existing.confirmed_at = now
                            else:
                                channel_id = next(
                                    (c.channel_id for c in campaigns if c.id == cid), None
                                )
                                session.add(SubscriptionEvent(
                                    campaign_id=cid,
                                    user_id=user_row2.id,
                                    channel_id=channel_id,
                                    status="confirmed",
                                    checked_at=now,
                                    confirmed_at=now,
                                ))
                        await session.commit()
            except Exception:
                logger.exception("[GATE] failed to save confirmations")

        # Все подписаны?
        if all_subscribed:
            try:
                await track(
                    "subscription_confirmed",
                    telegram_id=from_user.id,
                    payload={"campaigns_count": len(campaigns), "source": "middleware"},
                )
            except Exception:
                pass
            return await handler(event, data)

        # Не все подписаны — показываем экран
        logger.info(
            f"[GATE] user={from_user.id} not fully subscribed "
            f"({len(not_subscribed)} of {len(campaigns)} missing)"
        )
        await self._send_gate(event, campaigns, from_user.id)
        return None

    # --------------------------------------------------------
    # Отправка экрана подписки
    # --------------------------------------------------------
    async def _send_gate(
        self,
        event: TelegramObject,
        campaigns: List[SubscriptionCampaign],
        user_id: int,
    ) -> None:
        kb = _build_multi_gate_kb(campaigns)
        text = _build_multi_gate_text(campaigns)

        sent = False

        if isinstance(event, CallbackQuery):
            try:
                await event.answer("❌ Сначала подпишись на все каналы", show_alert=True)
            except Exception as e:
                logger.warning(f"[GATE] callback.answer failed: {e}")

            try:
                await event.message.answer(text, reply_markup=kb)
                sent = True
                logger.info(f"[GATE] sent to callback for user {user_id}")
            except Exception as e:
                logger.exception(f"[GATE] callback message send failed: {e}")

        elif isinstance(event, Message):
            try:
                await event.answer(text, reply_markup=kb)
                sent = True
                logger.info(f"[GATE] sent to message for user {user_id}")
            except Exception as e:
                logger.exception(f"[GATE] message send failed: {e}")

        if not sent:
            logger.error(f"[GATE] FAILED to deliver gate to user {user_id}")

        try:
            await track(
                "subscription_gate_shown",
                telegram_id=user_id,
                payload={
                    "campaigns": [c.id for c in campaigns],
                    "sent": sent,
                },
            )
        except Exception:
            pass