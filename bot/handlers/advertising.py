from datetime import datetime

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select

from database.connection import async_session
from database.models import AdvertisingCampaign, User, UserAdEvent
from services.analytics.tracker import track
from utils.logging import get_logger

router = Router()
logger = get_logger(__name__)


@router.callback_query(F.data.startswith("ad_click_"))
async def cb_ad_click(callback: CallbackQuery):
    await callback.answer()
    campaign_id = int(callback.data.replace("ad_click_", ""))

    async with async_session() as session:
        campaign = (await session.execute(
            select(AdvertisingCampaign).where(AdvertisingCampaign.id == campaign_id)
        )).scalar_one_or_none()

        user = (await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )).scalar_one_or_none()

        if campaign is None or user is None:
            await callback.message.answer("Кампания недоступна.")
            return

        # Найти последнее показывание и отметить клик
        event = (await session.execute(
            select(UserAdEvent)
            .where(UserAdEvent.campaign_id == campaign_id)
            .where(UserAdEvent.user_id == user.id)
            .order_by(UserAdEvent.id.desc())
            .limit(1)
        )).scalar_one_or_none()

        if event and event.clicked_at is None:
            event.clicked_at = datetime.utcnow()
            campaign.clicks += 1
            await session.commit()

        target_url = campaign.target_url

    await track("ad_clicked", telegram_id=callback.from_user.id, payload={"campaign_id": campaign_id})

    if target_url:
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🔗 Перейти", url=target_url)],
            ]
        )
        await callback.message.answer(
            "Спасибо за интерес! Перейти по ссылке:",
            reply_markup=kb,
        )
    else:
        await callback.message.answer("Спасибо! 👍")