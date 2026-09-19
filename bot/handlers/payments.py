from datetime import datetime, timedelta, timezone

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select

from bot.keyboards.main import pro_menu_kb
from database.connection import async_session
from database.models import Payment as PaymentModel, Promocode, User
from services.achievements import unlock_achievement
from services.analytics.tracker import track
from services.feature_flags import is_enabled
from utils.logging import get_logger

router = Router()
logger = get_logger(__name__)


@router.message(F.text == "💎 PRO")
async def pro_menu(message: Message):
    if not await is_enabled("premium_enabled", default=False):
        await message.answer(
            "💎 <b>PRO подписка</b>\n\n"
            "Сейчас подписка временно недоступна.\n"
            "Следи за обновлениями!"
        )
        return

    await message.answer(
        "💎 <b>PRO подписка</b>\n\n"
        "Что даёт PRO:\n"
        "• ♾ Безлимит AI-анализов (вместо 5 в день)\n"
        "• 🚀 Расширенные режимы поиска игроков\n"
        "• 🤖 AI-помощник в чатах\n"
        "• 🚫 Без рекламы\n\n"
        "Стоимость: <b>299 ₽ / 30 дней</b>",
        reply_markup=pro_menu_kb(),
    )


@router.callback_query(F.data == "pro_menu")
async def cb_pro_menu(callback: CallbackQuery):
    await callback.answer()
    if not await is_enabled("premium_enabled", default=False):
        await callback.message.answer(
            "💎 <b>PRO подписка</b>\n\nСейчас подписка временно недоступна."
        )
        return
    await callback.message.answer(
        "💎 <b>PRO подписка</b>\n\n"
        "Что даёт PRO:\n"
        "• ♾ Безлимит AI-анализов\n"
        "• 🚀 Расширенные режимы поиска\n"
        "• 🤖 AI-помощник в чатах\n"
        "• 🚫 Без рекламы\n\n"
        "Стоимость: <b>299 ₽ / 30 дней</b>",
        reply_markup=pro_menu_kb(),
    )


@router.callback_query(F.data == "buy_pro")
async def cb_buy_pro(callback: CallbackQuery):
    await callback.answer()

    if not await is_enabled("premium_enabled", default=False):
        await callback.message.answer("PRO отключён.")
        return

    from config import config

    if not config.YOOKASSA_SHOP_ID or not config.YOOKASSA_SECRET:
        await callback.message.answer(
            "💳 <b>Оплата временно недоступна</b>\n\n"
            "Платёжная система пока не подключена.\n\n"
            "Ты можешь активировать PRO через промокод — "
            "спроси у администратора или найди промокод в канале."
        )
        return

    async with async_session() as session:
        user = (await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )).scalar_one_or_none()
        if not user:
            await callback.message.answer("Сначала отправь фото.")
            return

    try:
        from services.payments.yookassa_client import create_pro_payment
        result = create_pro_payment(user.id, amount=299.0)
    except Exception:
        logger.exception("Payment creation failed")
        await callback.message.answer(
            "❌ Не удалось создать платёж. Попробуй позже или используй промокод."
        )
        return

    async with async_session() as session:
        session.add(PaymentModel(
            user_id=user.id,
            yookassa_payment_id=result["id"],
            amount=299.0,
            currency="RUB",
            status="pending",
            payment_type="pro",
            description="PRO подписка",
        ))
        await session.commit()

    await callback.message.answer(
        f"💳 Перейди по ссылке для оплаты:\n{result['confirmation_url']}\n\n"
        f"После оплаты PRO активируется автоматически."
    )


@router.callback_query(F.data == "enter_promo")
async def cb_enter_promo(callback: CallbackQuery):
    await callback.answer()
    await callback.message.answer(
        "🎟 Отправь промокод одним сообщением (например, <code>START50</code>)."
    )


@router.message(F.text.regexp(r"^[A-Z0-9]{4,32}$"))
async def handle_promo(message: Message):
    code = message.text.strip().upper()

    async with async_session() as session:
        promo = (await session.execute(
            select(Promocode).where(Promocode.code == code)
        )).scalar_one_or_none()

        if not promo or not promo.is_active:
            return

        if promo.max_uses and promo.used_count >= promo.max_uses:
            await message.answer("❌ Промокод исчерпан.")
            return

        if promo.expires_at and promo.expires_at < datetime.now(timezone.utc):
            await message.answer("❌ Промокод истёк.")
            return

        user = (await session.execute(
            select(User).where(User.telegram_id == message.from_user.id)
        )).scalar_one_or_none()

        if not user:
            await message.answer("Сначала отправь фото.")
            return

        days = promo.value if promo.type == "pro_days" else 30
        now = datetime.now(timezone.utc)
        base = user.premium_until if (user.premium_until and user.premium_until > now) else now
        user.premium_until = base + timedelta(days=days)
        promo.used_count += 1
        await session.commit()

        user_id_for_ach = user.id
        premium_until = user.premium_until

    await unlock_achievement(user_id_for_ach, "pro_first")
    await track("pro_purchase", telegram_id=message.from_user.id, payload={"type": "promo", "code": code})

    await message.answer(
        f"✅ <b>PRO активирован!</b>\n\n"
        f"Активирован на <b>{days} дней</b>.\n"
        f"Действует до: <b>{premium_until.strftime('%d.%m.%Y')}</b>"
    )