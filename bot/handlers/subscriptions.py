from datetime import datetime, timezone
from typing import List

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

MAX_CAMPAIGNS = 3


async def maybe_offer_subscription(bot, telegram_id: int) -> None:
    """Не используется, гейт в middleware."""
    return


def _build_channel_url(campaign: SubscriptionCampaign) -> str:
    url = campaign.channel_link
    if url and url.startswith("http"):
        return url
    if campaign.channel_username:
        username = campaign.channel_username.lstrip("@")
        return f"https://t.me/{username}"
    return "https://t.me/telegram"


def _build_multi_gate_kb(campaigns: List[SubscriptionCampaign]) -> InlineKeyboardMarkup:
    rows = []
    for c in campaigns:
        url = _build_channel_url(c)
        label = c.name or c.channel_username or "Канал"
        if len(label) > 28:
            label = label[:26] + "…"
        rows.append([InlineKeyboardButton(text=f"📢 {label}", url=url)])

    rows.append([InlineKeyboardButton(
        text="✅ Я подписался на все",
        callback_data="sub_check_all",
    )])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ============================================================
# Проверка подписки — после нажатия «✅ Я подписался на все»
# ============================================================
@router.callback_query(F.data == "sub_check_all")
async def cb_sub_check_all(callback: CallbackQuery):
    await callback.answer("Проверяю…")

    if not await is_enabled("mandatory_subscriptions_enabled", default=False):
        await callback.message.answer("Функция временно отключена.")
        return

    async with async_session() as session:
        user = (await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )).scalar_one_or_none()

        campaigns = list((await session.execute(
            select(SubscriptionCampaign)
            .where(SubscriptionCampaign.is_active.is_(True))
            .where(SubscriptionCampaign.channel_id.isnot(None))
            .order_by(SubscriptionCampaign.id.asc())
            .limit(MAX_CAMPAIGNS)
        )).scalars().all())

    if not campaigns:
        await callback.message.answer("Нет активных кампаний.")
        return

    if user is None:
        await callback.message.answer("Сначала отправь /start.")
        return

    # Проверяем каждый канал
    subscribed: List[SubscriptionCampaign] = []
    not_subscribed: List[SubscriptionCampaign] = []

    for c in campaigns:
        ok = await is_subscribed(callback.bot, callback.from_user.id, c.channel_id)
        if ok:
            subscribed.append(c)
        else:
            not_subscribed.append(c)

    # Сохраняем подтверждённые
    if subscribed:
        async with async_session() as session:
            now = datetime.now(timezone.utc)
            for c in subscribed:
                existing = (await session.execute(
                    select(SubscriptionEvent)
                    .where(SubscriptionEvent.campaign_id == c.id)
                    .where(SubscriptionEvent.user_id == user.id)
                )).scalar_one_or_none()

                if existing:
                    if existing.status != "confirmed":
                        existing.status = "confirmed"
                        existing.checked_at = now
                        existing.confirmed_at = now
                else:
                    session.add(SubscriptionEvent(
                        campaign_id=c.id,
                        user_id=user.id,
                        channel_id=c.channel_id,
                        status="confirmed",
                        checked_at=now,
                        confirmed_at=now,
                    ))

                # Считаем только первое подтверждение
                if not existing:
                    cmp_row = (await session.execute(
                        select(SubscriptionCampaign).where(SubscriptionCampaign.id == c.id)
                    )).scalar_one_or_none()
                    if cmp_row:
                        cmp_row.confirmed_subscribers += 1

            await session.commit()

    # Все подписаны?
    if not not_subscribed:
        await track(
            "subscription_confirmed",
            telegram_id=callback.from_user.id,
            payload={"campaigns_count": len(campaigns)},
        )

        try:
            await callback.message.edit_text(
                "🎉 <b>Спасибо за подписки!</b>\n\n"
                "Теперь тебе доступны все функции бота.\n\n"
                "📸 Отправь фото — получишь смешной AI-профиль."
            )
        except Exception:
            pass

        await callback.message.answer(
            "👋 <b>Добро пожаловать!</b>\n\n"
            "Отправь мне фотографию — и я сделаю тебе смешной игровой профиль.\n\n"
            "📸 <b>Просто отправь фото прямо в чат!</b>",
            reply_markup=main_menu_kb(),
        )
        return

    # Не все подписаны
    missing_lines = [
        "❌ <b>Ты ещё не подписан на:</b>\n"
    ]
    for c in not_subscribed:
        url = _build_channel_url(c)
        label = c.name or c.channel_username or "Канал"
        missing_lines.append(f"• <b>{label}</b>\n  👉 {url}")

    missing_lines.append("\nПодпишись и нажми «✅ Я подписался на все» ещё раз.")

    kb = _build_multi_gate_kb(campaigns)
    try:
        await callback.message.edit_text("\n".join(missing_lines), reply_markup=kb)
    except Exception:
        await callback.message.answer("\n".join(missing_lines), reply_markup=kb)