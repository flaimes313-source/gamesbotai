import asyncio
import os
import random
from datetime import datetime, timedelta, timezone
from typing import Optional

from aiohttp import web
from sqlalchemy import select

from config import config
from database.connection import async_session
from database.models import Payment, User
from services.analytics.tracker import track
from utils.logging import get_logger, setup_logging

logger = get_logger(__name__)


# ============================================================
# Длительность тарифов PRO (в днях)
# ============================================================
PRO_PLAN_DAYS = {
    1: 30,
    6: 180,
    12: 365,
}
PRO_DEFAULT_DAYS = 30


# ============================================================
# Глобальный bot (пробрасывается из main.py)
# ============================================================
_bot = None


def set_bot(bot) -> None:
    """Устанавливает глобальный bot для отправки уведомлений."""
    global _bot
    _bot = bot
    logger.info("[WEBHOOK] bot attached")


# ============================================================
# Сообщения после активации PRO
# ============================================================
PRO_ACTIVATED_MESSAGES = [
    (
        "💎 <b>PRO АКТИВИРОВАН!</b>\n\n"
        "Ты только что открыл себе максимум:\n"
        "♾ 50 анализов в день\n"
        "🚀 Расширенные режимы поиска\n"
        "🤖 AI-помощник в чатах\n"
        "🚫 Никакой рекламы\n\n"
        "📸 <b>Прокачай харизму максимально</b> — "
        "отправь новое фото и смотри, какой ты вайб!"
    ),
    (
        "💎 <b>PRO на борту!</b>\n\n"
        "Теперь ты играешь без ограничений:\n"
        "♾ Анализы без лимита\n"
        "🚀 Секретные режимы поиска\n"
        "🤖 AI-помощник в чатах\n"
        "🚫 Реклама больше не пристаёт\n\n"
        "🔥 <b>Твой хаос станет легендарным.</b> "
        "Отправь фото — сравним!"
    ),
    (
        "💎 <b>PRO активен!</b>\n\n"
        "Что теперь доступно:\n"
        "♾ 50 анализов в день\n"
        "🚀 Режимы для настоящих игроков\n"
        "🤖 AI-помощник в чатах\n"
        "🚫 Чисто, без рекламы\n\n"
        "⚡ <b>Время прокачать вайб до максимума.</b> "
        "Жду фото!"
    ),
]


def _pick_activated_message() -> str:
    return random.choice(PRO_ACTIVATED_MESSAGES)


# ============================================================
# Выдача PRO
# ============================================================
async def _grant_pro(
    user_id: int,
    payment_id: str,
    months: int = 1,
) -> bool:
    """
    Выдаёт PRO на N месяцев (1 / 6 / 12).
    Если PRO уже активна — продлевает.
    После — отправляет поздравительное сообщение.

    ВАЖНО: months передаётся из metadata YooKassa.
    Если months неизвестен — используется 30 дней (fallback).
    """
    days = PRO_PLAN_DAYS.get(months, PRO_DEFAULT_DAYS)

    async with async_session() as session:
        user = (await session.execute(
            select(User).where(User.id == user_id)
        )).scalar_one_or_none()

        if user is None:
            logger.warning(f"[YOOKASSA] User {user_id} not found for PRO grant")
            return False

        now = datetime.now(timezone.utc)
        base = user.premium_until if (user.premium_until and user.premium_until > now) else now
        user.premium_until = base + timedelta(days=days)

        telegram_id = user.telegram_id
        premium_until = user.premium_until

        await session.commit()

    logger.info(
        f"[YOOKASSA] PRO granted user={user_id} months={months} days={days} "
        f"until={premium_until} (payment {payment_id})"
    )

    # Пишем в Payment, сколько дней начислили (для отчётности)
    try:
        async with async_session() as session:
            payment = (await session.execute(
                select(Payment).where(Payment.yookassa_payment_id == payment_id)
            )).scalar_one_or_none()
            if payment:
                payment.months = months
                payment.days_granted = days
                await session.commit()
    except Exception:
        logger.exception("[YOOKASSA] failed to save months/days in Payment")

    # Аналитика
    try:
        await track(
            "pro_purchase",
            telegram_id=telegram_id,
            payload={
                "type": "yookassa",
                "payment_id": payment_id,
                "months": months,
                "days_granted": days,
            },
        )
    except Exception:
        logger.exception("[YOOKASSA] track failed")

    # Поздравительное сообщение
    if _bot is not None:
        try:
            until_str = premium_until.strftime("%d.%m.%Y")
            await _bot.send_message(
                telegram_id,
                _pick_activated_message()
                + f"\n\n📅 PRO активна до: <b>{until_str}</b> ({days} дней)",
            )
        except Exception:
            logger.exception("[YOOKASSA] failed to send activation message")
    else:
        logger.warning("[YOOKASSA] bot not attached, message not sent")

    return True


# ============================================================
# Webhook YooKassa
# ============================================================
async def handle_yookassa_webhook(request: web.Request) -> web.Response:
    """
    Принимает webhook от YooKassa.
    События: payment.succeeded, payment.canceled, refund.succeeded.
    Защита от повторной обработки — по Payment.status.
    """
    try:
        data = await request.json()
    except Exception:
        logger.exception("[YOOKASSA] bad JSON in webhook")
        return web.json_response({"status": "bad_request"}, status=400)

    event = data.get("event", "")
    obj = data.get("object", {}) or {}
    payment_id = obj.get("id")
    status = obj.get("status")
    metadata = obj.get("metadata", {}) or {}
    user_id_meta = metadata.get("user_id")
    months = int(metadata.get("months", 1) or 1)

    logger.info(
        f"[YOOKASSA] webhook event={event} payment_id={payment_id} "
        f"status={status} meta_user={user_id_meta} months={months}"
    )

    # ---------- payment.succeeded ----------
    if event == "payment.succeeded" and payment_id:
        resolved_user_id = None

        async with async_session() as session:
            payment = (await session.execute(
                select(Payment).where(Payment.yookassa_payment_id == payment_id)
            )).scalar_one_or_none()

            if payment is None:
                logger.warning(f"[YOOKASSA] payment {payment_id} not found in DB")
                return web.json_response({"status": "not_found"}, status=404)

            if payment.status == "succeeded":
                logger.info(f"[YOOKASSA] payment {payment_id} already processed")
                return web.json_response({"status": "already_processed"})

            payment.status = "succeeded"
            payment.paid_at = datetime.now(timezone.utc)
            await session.commit()
            resolved_user_id = payment.user_id

        if resolved_user_id:
            await _grant_pro(resolved_user_id, payment_id, months=months)

        return web.json_response({"status": "ok"})

    # ---------- payment.canceled ----------
    if event == "payment.canceled" and payment_id:
        async with async_session() as session:
            payment = (await session.execute(
                select(Payment).where(Payment.yookassa_payment_id == payment_id)
            )).scalar_one_or_none()

            if payment and payment.status != "succeeded":
                payment.status = "canceled"
                await session.commit()
                logger.info(f"[YOOKASSA] payment {payment_id} canceled")

        return web.json_response({"status": "ok"})

    # ---------- refund.succeeded ----------
    if event == "refund.succeeded" and payment_id:
        async with async_session() as session:
            payment = (await session.execute(
                select(Payment).where(Payment.yookassa_payment_id == payment_id)
            )).scalar_one_or_none()

            if payment:
                payment.status = "refunded"
                await session.commit()
                logger.info(f"[YOOKASSA] payment {payment_id} refunded")

        return web.json_response({"status": "ok"})

    return web.json_response({"status": "ignored"})


# ============================================================
# Health-check
# ============================================================
async def handle_health(request: web.Request) -> web.Response:
    checks = {"web": "ok"}
    status_code = 200

    try:
        async with async_session() as session:
            await session.execute(select(1))
        checks["db"] = "ok"
    except Exception as e:
        checks["db"] = f"error: {e.__class__.__name__}"
        status_code = 503

    return web.json_response(
        {
            "status": "healthy" if status_code == 200 else "degraded",
            "checks": checks,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
        status=status_code,
    )


async def handle_root(request: web.Request) -> web.Response:
    return web.json_response({"service": "ai_social_bot", "status": "running"})


# ============================================================
# Запуск
# ============================================================
def create_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/", handle_root)
    app.router.add_get("/health", handle_health)
    app.router.add_get("/healthz", handle_health)
    app.router.add_post("/yookassa/webhook", handle_yookassa_webhook)
    return app


async def run_server(port: int = 8080) -> None:
    app = create_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"Webhook server started on port {port}")


if __name__ == "__main__":
    setup_logging()
    port = int(os.getenv("PORT", "8080"))
    asyncio.run(run_server(port))