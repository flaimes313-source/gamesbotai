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
from services.premium import is_premium
from utils.logging import get_logger

router = Router()
logger = get_logger(__name__)


# ============================================================
# Тарифы PRO
# ============================================================
PRO_PLANS = {
    "1m": {"months": 1, "days": 30, "price": 390, "label": "1 месяц"},
    "6m": {"months": 6, "days": 180, "price": 1990, "label": "6 месяцев (-15%)"},
    "12m": {"months": 12, "days": 365, "price": 3490, "label": "12 месяцев (-25%)"},
}


PRO_DESCRIPTION = (
    "💎 <b>PRO подписка</b>\n\n"
    "Получи максимум от бота:\n\n"
    "♾ <b>Безлимитные AI-анализы</b>\n"
    "   <i>50 вместо 1 в день</i>\n\n"
    "🚀 <b>Расширенные режимы поиска</b>\n"
    "   <i>«Интеллектуальный соперник» и «Максимальный хаос»</i>\n\n"
    "🤖 <b>AI-помощник в чатах</b>\n"
    "   <i>3 варианта ответа от AI + анализ переписки</i>\n\n"
    "🚫 <b>Без рекламы</b>\n"
    "   <i>Никаких рекламных вставок</i>\n\n"
    "🎁 <b>Без обязательных подписок</b>\n"
    "   <i>Не нужно подписываться на каналы партнёров</i>"
)


# ============================================================
# МЕНЮ PRO
# ============================================================
@router.message(F.text == "💎 PRO")
async def pro_menu_message(message: Message):
    await _show_pro_menu(message, message.from_user.id)


@router.callback_query(F.data == "pro_menu")
async def cb_pro_menu(callback: CallbackQuery):
    await callback.answer()
    await _show_pro_menu(callback.message, callback.from_user.id)


async def _show_pro_menu(message: Message, telegram_id: int):
    premium = await is_premium(telegram_id)

    if premium:
        async with async_session() as session:
            user = (await session.execute(
                select(User).where(User.telegram_id == telegram_id)
            )).scalar_one_or_none()
            until = user.premium_until if user else None

        if until:
            until_str = until.strftime("%d.%m.%Y")
            days_left = max(0, (until - datetime.now(timezone.utc)).days)
            status = (
                f"✅ <b>PRO активна</b>\n"
                f"📅 До: <b>{until_str}</b> ({days_left} дн.)\n\n"
            )
        else:
            status = "✅ <b>PRO активна</b>\n\n"
    else:
        status = "⚪ <b>PRO не активна</b>\n\n"

    text = status + PRO_DESCRIPTION + "\n\n" + "💰 <b>Выбери тариф:</b>"

    try:
        await message.answer(text, reply_markup=pro_menu_kb(is_premium=premium))
    except Exception:
        await message.answer(text, reply_markup=pro_menu_kb(is_premium=premium))


# ============================================================
# ПОКУПКА PRO — три тарифа
# ============================================================
@router.callback_query(F.data.startswith("buy_pro_"))
async def cb_buy_pro(callback: CallbackQuery):
    await callback.answer()

    plan_key = callback.data.replace("buy_pro_", "")
    plan = PRO_PLANS.get(plan_key)
    if not plan:
        await callback.message.answer("Тариф не найден.")
        return

    if not await is_enabled("premium_enabled", default=False):
        await callback.message.answer(
            "💎 <b>PRO пока недоступна</b>\n\n"
            "Мы готовим запуск в ближайшее время."
        )
        return

    from config import config
    if not config.YOOKASSA_SHOP_ID or not config.YOOKASSA_SECRET:
        await callback.message.answer(
            "💳 <b>Оплата временно недоступна</b>\n\n"
            "Платёжная система пока не подключена.\n\n"
            "Ты можешь активировать PRO через промокод — "
            "спроси у администратора."
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
        result = create_pro_payment(
            user.id,
            amount=float(plan["price"]),
            description=f"PRO {plan['label']}",
            months=plan["months"],
        )
    except Exception:
        logger.exception("Payment creation failed")
        await callback.message.answer("❌ Не удалось создать платёж. Попробуй позже.")
        return

    async with async_session() as session:
        session.add(PaymentModel(
            user_id=user.id,
            yookassa_payment_id=result["id"],
            amount=float(plan["price"]),
            currency="RUB",
            status="pending",
            payment_type="pro",
            description=f"PRO {plan['label']}",
        ))
        await session.commit()

    await callback.message.answer(
        f"💳 <b>Оплата PRO</b>\n\n"
        f"Тариф: <b>{plan['label']}</b>\n"
        f"Сумма: <b>{plan['price']} ₽</b>\n"
        f"Срок: <b>{plan['days']} дней</b>\n\n"
        f"Перейди по ссылке:\n{result['confirmation_url']}\n\n"
        f"После оплаты PRO активируется автоматически."
    )


# ============================================================
# ПОДАРОК PRO ДРУГУ
# ============================================================
@router.callback_query(F.data == "gift_pro")
async def cb_gift_pro(callback: CallbackQuery):
    await callback.answer()
    await callback.message.answer(
        "🎁 <b>Подарить PRO</b>\n\n"
        "Скоро! Мы работаем над функцией подарочных подписок.\n\n"
        "А пока ты можешь создать промокод у администратора "
        "и передать его другу."
    )


# ============================================================
# ПРОМОКОДЫ
# ============================================================
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
    await track(
        "pro_purchase",
        telegram_id=message.from_user.id,
        payload={"type": "promo", "code": code, "days": days},
    )

    await message.answer(
        f"✅ <b>PRO активирован!</b>\n\n"
        f"Активирован на <b>{days} дней</b>.\n"
        f"Действует до: <b>{premium_until.strftime('%d.%m.%Y')}</b>"
    )