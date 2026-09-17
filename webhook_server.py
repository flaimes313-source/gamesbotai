import asyncio
import os
from datetime import datetime, timedelta

from aiohttp import web
from sqlalchemy import select

from config import config
from database.connection import async_session
from database.models import Payment, User
from services.analytics.tracker import track
from utils.logging import get_logger, setup_logging

logger = get_logger(__name__)

PRO_DURATION_DAYS = 30


# ============================================================
# Утилиты
# ============================================================
async def _grant_pro(user_id: int, payment_id: str) -> bool:
    """Выдаёт PRO и логирует. Возвращает True при успехе."""
    async with async_session() as session:
        user = (await session.execute(
            select(User).where(User.id == user_id)
        )).scalar_one_or_none()
        if user is None:
            logger.warning(f"User {user_id} not found for PRO grant")
            return False

        now = datetime.utcnow()
        base = user.premium_until if (user.premium_until and user.premium_until > now) else now
        user.premium_until = base + timedelta(days=PRO_DURATION_DAYS)

        await session.commit()
        logger.info(f"PRO granted to user {user_id} until {user.premium_until} (payment {payment_id})")

    await track("pro_purchase", telegram_id=user.telegram_id, payload={"type": "yookassa", "payment_id": payment_id})
    return True


# ============================================================
# Обработчики webhook YooKassa
# ============================================================
async def handle_yookassa_webhook(request: web.Request) -> web.Response:
    """
    Принимает webhook от YooKassa.
    Обрабатывает события: payment.succeeded, payment.canceled, refund.succeeded.
    Защита от повторной обработки через статус в БД.
    """
    try:
        data = await request.json()
    except Exception:
        logger.exception("Webhook: bad JSON")
        return web.json_response({"status": "bad_request"}, status=400)

    event = data.get("event", "")
    obj = data.get("object", {}) or {}
    payment_id = obj.get("id")
    status = obj.get("status")
    metadata = obj.get("metadata", {}) or {}
    user_id = metadata.get("user_id")

    logger.info(f"Webhook received: event={event} payment_id={payment_id} status={status}")

    # ---------- payment.succeeded ----------
    if event == "payment.succeeded" and payment_id:
        async with async_session() as session:
            payment = (await session.execute(
                select(Payment).where(Payment.yookassa_payment_id == payment_id)
            )).scalar_one_or_none()

            if payment is None:
                logger.warning(f"Payment {payment_id} not found in DB")
                return web.json_response({"status": "not_found"}, status=404)

            if payment.status == "succeeded":
                logger.info(f"Payment {payment_id} already processed")
                return web.json_response({"status": "already_processed"})

            payment.status = "succeeded"
            payment.paid_at = datetime.utcnow()
            await session.commit()
            resolved_user_id = payment.user_id

        if resolved_user_id:
            await _grant_pro(resolved_user_id, payment_id)

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
                logger.info(f"Payment {payment_id} canceled")

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
                logger.info(f"Payment {payment_id} refunded")

        return web.json_response({"status": "ok"})

    return web.json_response({"status": "ignored"})


# ============================================================
# Health-check (для BotHost и мониторинга)
# ============================================================
async def handle_health(request: web.Request) -> web.Response:
    """Liveness/readiness probe для хостинга."""
    checks = {"web": "ok"}
    status_code = 200

    # БД доступна?
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
            "timestamp": datetime.utcnow().isoformat(),
        },
        status=status_code,
    )


async def handle_root(request: web.Request) -> web.Response:
    """Корень — простая страница, чтобы хостинг не ругался."""
    return web.json_response({"service": "ai_social_bot", "status": "running"})


# ============================================================
# Запуск сервера
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