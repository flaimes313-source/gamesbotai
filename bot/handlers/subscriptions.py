from datetime import datetime, timedelta

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select

from config import config
from database.connection import async_session
from database.models import SubscriptionCampaign, SubscriptionEvent, User
from services.analytics.tracker import track
from services.subscriptions.checker import is_subscribed
from services.whitelist import is_whitelisted
from utils.logging import get_logger

router = Router()
logger = get_logger(__name__)

OFFER_COOLDOWN_DAYS = 7


async def maybe_offer_subscription(bot, telegram_id: int) -> None:
    """
    Показывает оффер обязательной подписки не чаще раза в 7 дней.
    Пропускает:
    - админов
    - пользователей в whitelist
    - тех, кто уже подтвердил подписку
    """
    if not config.MANDATORY_SUBSCRIPTIONS:
        return

    # Админы не видят оффер
    if telegram_id in config.ADMIN_IDS:
        return

    # Whitelist — пропуск
    if await is_whitelisted(telegram_id):
        logger.info(f"Subscription offer skipped: {telegram_id} in whitelist")
        return

    async with async_session() as session:
        user = (await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )).scalar_one_or_none()
        if user is None:
            return

        now = datetime.utcnow()

        if user.last_subscription_offer and (now - user.last_subscription_offer) < timedelta(days=OFFER_COOLDOWN_DAYS):
            return

        campaign = (await session.execute(
            select(SubscriptionCampaign)
            .where(SubscriptionCampaign.is_active.is_(True))
            .limit(1)
        )).scalar_one_or_none()

        if campaign is None:
            return

        existing = (await session.execute(
            select(SubscriptionEvent).where(
                SubscriptionEvent.campaign_id == campaign.id,
                SubscriptionEvent.user_id == user.id,
                SubscriptionEvent.status == "confirmed",
            )
        )).scalar_one_or_none()

        if existing:
            return

        user.last_subscription_offer = now
        await session.commit()

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="📢 Подписаться",
                url=campaign.channel_link or "https://t.me/",
            )],
            [InlineKeyboardButton(
                text="✅ Проверить подписку",
                callback_data=f"sub_check_{campaign.id}",
            )],
        ]
    )

    try:
        await bot.send_message(
            telegram_id,
            "🎁 <b>Для тебя новая возможность!</b>\n\n"
            "Хочешь узнать, кто из игроков максимально похож на тебя?\n"
            "Подпишись на канал партнёра, чтобы открыть функцию.",
            reply_markup=kb,
        )
        await track("subscription_offer_shown", telegram_id=telegram_id, payload={"campaign_id": campaign.id})
    except Exception:
        logger.exception("Subscription offer send failed")


@router.callback_query(F.data.startswith("sub_check_"))
async def cb_sub_check(callback: CallbackQuery):
    await callback.answer()
    campaign_id = int(callback.data.replace("sub_check_", ""))

    async with async_session() as session:
        campaign = (await session.execute(
            select(SubscriptionCampaign).where(SubscriptionCampaign.id == campaign_id)
        )).scalar_one_or_none()
        user = (await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )).scalar_one_or_none()

    if not campaign or not user:
        await callback.message.answer("Кампания недоступна.")
        return

    if not campaign.channel_id:
        await callback.message.answer("⚠️ Кампания настроена некорректно (нет channel_id).")
        return

    ok = await is_subscribed(callback.bot, callback.from_user.id, campaign.channel_id)
    if not ok:
        await callback.message.answer("❌ Пока не вижу подписку. Подпишись и попробуй снова.")
        return

    async with async_session() as session:
        existing = (await session.execute(
            select(SubscriptionEvent).where(
                SubscriptionEvent.campaign_id == campaign.id,
                SubscriptionEvent.user_id == user.id,
            )
        )).scalar_one_or_none()

        if existing and existing.status == "confirmed":
            await callback.message.answer("✅ Подписка уже подтверждена ранее.")
            return

        if existing:
            existing.status = "confirmed"
            existing.checked_at = datetime.utcnow()
            existing.confirmed_at = datetime.utcnow()
        else:
            session.add(SubscriptionEvent(
                campaign_id=campaign.id,
                user_id=user.id,
                channel_id=campaign.channel_id,
                status="confirmed",
                checked_at=datetime.utcnow(),
                confirmed_at=datetime.utcnow(),
            ))

        cmp_row = (await session.execute(
            select(SubscriptionCampaign).where(SubscriptionCampaign.id == campaign.id)
        )).scalar_one_or_none()
        if cmp_row:
            cmp_row.confirmed_subscribers += 1

        await session.commit()

    await track("subscription_confirmed", telegram_id=callback.from_user.id, payload={"campaign_id": campaign_id})
    await callback.message.answer("🎉 Спасибо! Функция разблокирована.")