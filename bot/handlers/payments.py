from datetime import datetime, timedelta

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select

from bot.keyboards.main import pro_menu_kb
from config import config
from database.connection import async_session
from database.models import Payment as PaymentModel, Promocode, User
from services.achievements import unlock_achievement
from services.analytics.tracker import track
from services.payments.yookassa_client import create_pro_payment
from utils.logging import get_logger

router = Router()
logger = get_logger(__name__)


@router.message(F.text == "💎 PRO")
async def pro_menu(message: Message):
    if not config.PREMIUM_ENABLED:
        await message.answer("💎 PRO временно отключён.")
        return
    await message.answer(
        "💎 <b>PRO подписка</b>\n\n"
        "• Больше AI-подсказок\n"
        "• Дополнительные тесты\n"
        "• Расширенный поиск игроков\n"
        "• Без рекламы",
        reply_markup=pro_menu_kb(),
    )


@router.callback_query(F.data == "pro_menu")
async def cb_pro_menu(callback: CallbackQuery):
    await callback.answer()
    if not config.PREMIUM_ENABLED:
        await callback.message.answer("PRO отключён.")
        return
    await callback.message.answer(
        "💎 <b>PRO подписка</b>\n\n"
        "• Больше AI-подсказок\n"
        "• Дополнительные тесты\n"
        "• Расширенный поиск игроков\n"
        "• Без рекламы",
        reply_markup=pro_menu_kb(),
    )


@router.callback_query(F.data == "buy_pro")
async def cb_buy_pro(callback: CallbackQuery):
    await callback.answer()
    if not config.PREMIUM_ENABLED:
        await callback.message.answer("PRO отключён.")
        return

    async with async_session() as session:
        user = (await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )).scalar_one_or_none()
        if not user:
            await callback.message.answer("Сначала отправь фото.")
            return

    try:
        result = create_pro_payment(user.id, amount=299.0)
    except Exception:
        logger.exception("Payment creation failed")
        await callback.message.answer("Ошибка оплаты. Попробуй позже.")
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
        f"💳 Перейди по ссылке для оплаты:\n{result['confirmation_url']}"
    )


@router.callback_query(F.data == "enter_promo")
async def cb_enter_promo(callback: CallbackQuery):
    await callback.answer()
    await callback.message.answer("Отправь промокод одним сообщением.")


@router.message(F.text.regexp(r"^[A-Z0-9]{4,32}$"))
async def handle_promo(message: Message):
    code = message.text.strip().upper()

    async with async_session() as session:
        promo = (await session.execute(
            select(Promocode).where(Promocode.code == code)
        )).scalar_one_or_none()

        if not promo or not promo.is_active:
            return  # молча игнорируем

        if promo.max_uses and promo.used_count >= promo.max_uses:
            await message.answer("❌ Промокод исчерпан.")
            return

        if promo.expires_at and promo.expires_at < datetime.utcnow():
            await message.answer("❌ Промокод истёк.")
            return

        user = (await session.execute(
            select(User).where(User.telegram_id == message.from_user.id)
        )).scalar_one_or_none()

        if not user:
            return

        days = promo.value if promo.type == "pro_days" else 30
        now = datetime.utcnow()
        base = user.premium_until if (user.premium_until and user.premium_until > now) else now
        user.premium_until = base + timedelta(days=days)
        promo.used_count += 1
        await session.commit()

        user_id_for_ach = user.id

    await unlock_achievement(user_id_for_ach, "pro_first")
    await track("pro_purchase", telegram_id=message.from_user.id, payload={"type": "promo", "code": code})

    await message.answer(f"✅ PRO активирован на {days} дней!")