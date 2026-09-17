from datetime import datetime, timedelta

from sqlalchemy import select

from config import config
from database.connection import async_session
from database.models import AdvertisingCampaign, User, UserAdEvent
from utils.logging import get_logger

logger = get_logger(__name__)

AD_COOLDOWN_DAYS = 7


async def maybe_send_ad(bot, telegram_id: int) -> bool:
    """
    Отправляет рекламу пользователю не чаще раза в 7 дней.
    PRO-пользователи рекламу не получают.
    Возвращает True, если реклама была отправлена.
    """
    if not config.ADVERTISING_ENABLED:
        return False

    async with async_session() as session:
        user = (await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )).scalar_one_or_none()

        if user is None:
            return False

        now = datetime.utcnow()

        # PRO — без рекламы
        if user.premium_until and user.premium_until > now:
            return False

        # Cooldown
        if user.last_ad_received and (now - user.last_ad_received) < timedelta(days=AD_COOLDOWN_DAYS):
            return False

        # Активная кампания
        campaign = (await session.execute(
            select(AdvertisingCampaign)
            .where(AdvertisingCampaign.status == "active")
            .order_by(AdvertisingCampaign.id)
            .limit(1)
        )).scalar_one_or_none()

        if campaign is None:
            return False

        # Лимит показов
        if campaign.impression_limit and campaign.sent_count >= campaign.impression_limit:
            return False

        # Бюджет (если задан price_per_impression)
        if campaign.price_per_impression and campaign.budget:
            spent = float(campaign.price_per_impression) * campaign.sent_count
            if spent >= float(campaign.budget):
                return False

        # Отправляем
        try:
            if campaign.image_file_id:
                await bot.send_photo(
                    telegram_id,
                    campaign.image_file_id,
                    caption=campaign.text,
                )
            else:
                await bot.send_message(telegram_id, campaign.text)
        except Exception:
            logger.exception("Ad send failed")
            return False

        # Логируем событие и обновляем счётчики
        campaign.sent_count += 1
        session.add(UserAdEvent(
            campaign_id=campaign.id,
            user_id=user.id,
            shown_at=now,
        ))
        user.last_ad_received = now
        await session.commit()

    logger.info(f"Ad sent to {telegram_id} (campaign_id={campaign.id})")
    return True


async def stop_campaign(campaign_id: int) -> None:
    """Остановить кампанию (для админки)."""
    async with async_session() as session:
        campaign = (await async_session().execute(
            select(AdvertisingCampaign).where(AdvertisingCampaign.id == campaign_id)
        )).scalar_one_or_none()
        if campaign:
            campaign.status = "stopped"
            campaign.ended_at = datetime.utcnow()
            await session.commit()
            logger.info(f"Campaign {campaign_id} stopped")