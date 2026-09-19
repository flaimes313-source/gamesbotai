from datetime import datetime, timedelta, timezone

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select

from config import config
from database.connection import async_session
from database.models import AdvertisingCampaign, User, UserAdEvent
from services.analytics.tracker import track
from services.feature_flags import is_enabled
from services.whitelist import is_whitelisted
from utils.logging import get_logger

logger = get_logger(__name__)

AD_COOLDOWN_DAYS = 7


def _ad_kb(campaign: AdvertisingCampaign) -> InlineKeyboardMarkup | None:
    if not campaign.target_url:
        return None
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="🔗 Подробнее",
                callback_data=f"ad_click_{campaign.id}",
            )],
        ]
    )


async def maybe_send_ad(bot, telegram_id: int) -> bool:
    if not await is_enabled("advertising_enabled", default=False):
        return False

    if telegram_id in config.ADMIN_IDS:
        return False

    if await is_whitelisted(telegram_id):
        return False

    async with async_session() as session:
        user = (await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )).scalar_one_or_none()
        if user is None:
            return False

        now = datetime.now(timezone.utc)

        if user.premium_until and user.premium_until > now:
            return False

        if user.last_ad_received and (now - user.last_ad_received) < timedelta(days=AD_COOLDOWN_DAYS):
            return False

        campaign = (await session.execute(
            select(AdvertisingCampaign)
            .where(AdvertisingCampaign.status == "active")
            .order_by(AdvertisingCampaign.id)
            .limit(1)
        )).scalar_one_or_none()

        if campaign is None:
            return False

        if campaign.impression_limit and campaign.sent_count >= campaign.impression_limit:
            return False

        if campaign.price_per_impression and campaign.budget:
            spent = float(campaign.price_per_impression) * campaign.sent_count
            if spent >= float(campaign.budget):
                return False

        campaign_id = campaign.id
        campaign_text = campaign.text
        campaign_image = campaign.image_file_id
        kb = _ad_kb(campaign)

        try:
            if campaign_image:
                await bot.send_photo(telegram_id, campaign_image, caption=campaign_text, reply_markup=kb)
            else:
                await bot.send_message(telegram_id, campaign_text, reply_markup=kb)
        except Exception:
            logger.exception("Ad send failed")
            return False

        campaign.sent_count += 1
        session.add(UserAdEvent(campaign_id=campaign.id, user_id=user.id, shown_at=now))
        user.last_ad_received = now
        await session.commit()

    await track("ad_shown", telegram_id=telegram_id, payload={"campaign_id": campaign_id})
    logger.info(f"Ad sent to {telegram_id} (campaign_id={campaign_id})")
    return True


async def stop_campaign(campaign_id: int) -> None:
    async with async_session() as session:
        campaign = (await session.execute(
            select(AdvertisingCampaign).where(AdvertisingCampaign.id == campaign_id)
        )).scalar_one_or_none()
        if campaign:
            campaign.status = "stopped"
            campaign.ended_at = datetime.now(timezone.utc)
            await session.commit()
            logger.info(f"Campaign {campaign_id} stopped")