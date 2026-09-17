from datetime import datetime, timedelta
from sqlalchemy import select

from database.connection import async_session
from database.models import AdvertisingCampaign, User, UserAdEvent
from config import config
from utils.logging import get_logger

logger = get_logger(__name__)


async def maybe_send_ad(bot, telegram_id: int) -> bool:
    if not config.ADVERTISING_ENABLED:
        return False

    async with async_session() as session:
        user = (await session.execute(select(User).where(User.telegram_id == telegram_id))).scalar_one_or_none()
        if not user:
            return False

        # не чаще раза в 7 дней
        if user.last_ad_received and (datetime.utcnow() - user.last_ad_received) < timedelta(days=7):
            return False

        campaign = (await session.execute(
            select(AdvertisingCampaign).where(AdvertisingCampaign.status == "active").limit(1)
        )).scalar_one_or_none()

        if not campaign:
            return False

        try:
            await bot.send_message(telegram_id, campaign.text)
        except Exception:
            logger.exception("Ad send failed")
            return False

        campaign.sent_count += 1
        session.add(UserAdEvent(campaign_id=campaign.id, user_id=user.id, shown_at=datetime.utcnow()))
        user.last_ad_received = datetime.utcnow()
        await session.commit()

    return True