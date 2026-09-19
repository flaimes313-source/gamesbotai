from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select

from bot.keyboards.main import main_menu_kb
from database.connection import async_session
from database.models import SubscriptionCampaign, SubscriptionEvent, User
from services.analytics.tracker import track
from services.feature_flags import is_enabled
from services.subscriptions.checker import is_subscribed
from utils.logging import get_logger

router = Router()
logger = get_logger(__name__)


async def maybe_offer_subscription(bot, telegram_id: int) -> None:
    """
    Пассивный оффер — больше не используется.
    Основной гейт теперь в MandatorySubscriptionMiddleware.
    """
    return


@router.callback_query(F.data.startswith("sub_check_"))
async def cb_sub_check(callback: CallbackQuery):
    await callback.answer("Проверяю подписку…")
    campaign_id = int(callback.data.replace("sub_check_", ""))

    if not await is_enabled("mandatory_subscriptions_enabled", default=False):
        await callback.message.answer("Функция временно отключена.")
        return

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
        await callback.message.answer("⚠️ Кампания настроена некорректно.")
        return

    channel_url = campaign.channel_link or (
        f"https://t.me/{campaign.channel_username}"
        if campaign.channel_username
        else "https://t.me/"
    )

    # Проверяем через Telegram
    ok = await is_subscribed(callback.bot, callback.from_user.id, campaign.channel_id)

    if not ok:
        await callback.message.answer(
            "❌ <b>Пока не вижу подписку</b>\n\n"
            f"Убедись, что ты подписан на канал:\n"
            f"👉 {channel_url}\n\n"
            "После подписки нажми «✅ Я подписался» снова.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="📢 Подписаться", url=channel_url)],
                    [InlineKeyboardButton(
                        text="✅ Я подписался",
                        callback_data=f"sub_check_{campaign.id}",
                    )],
                ]
            ),
        )
        return

    # Сохраняем подтверждение
    async with async_session() as session:
        existing = (await session.execute(
            select(SubscriptionEvent).where(
                SubscriptionEvent.campaign_id == campaign.id,
                SubscriptionEvent.user_id == user.id,
            )
        )).scalar_one_or_none()

        now = datetime.now(timezone.utc)

        if existing:
            existing.status = "confirmed"
            existing.checked_at = now
            existing.confirmed_at = now
        else:
            session.add(SubscriptionEvent(
                campaign_id=campaign.id,
                user_id=user.id,
                channel_id=campaign.channel_id,
                status="confirmed",
                checked_at=now,
                confirmed_at=now,
            ))

        cmp_row = (await session.execute(
            select(SubscriptionCampaign).where(SubscriptionCampaign.id == campaign.id)
        )).scalar_one_or_none()
        if cmp_row:
            cmp_row.confirmed_subscribers += 1

        await session.commit()

    await track(
        "subscription_confirmed",
        telegram_id=callback.from_user.id,
        payload={"campaign_id": campaign_id},
    )

    try:
        await callback.message.edit_text(
            "🎉 <b>Спасибо за подписку!</b>\n\n"
            "Теперь тебе доступны все функции бота.\n\n"
            "📸 Отправь фото — получишь смешной AI-профиль.",
        )
    except Exception:
        pass

    await callback.message.answer(
        "👋 <b>Добро пожаловать!</b>\n\n"
        "Отправь мне фотографию — и я сделаю тебе смешной игровой профиль.\n\n"
        "📸 <b>Просто отправь фото прямо в чат!</b>\n\n"
        "Кнопки внизу — профиль, поиск игроков, сравнение с друзьями, "
        "настройки и другое.",
        reply_markup=main_menu_kb(),
    )