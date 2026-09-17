import asyncio
from datetime import datetime, timedelta

from aiohttp import web

from config import config
from database.connection import async_session
from database.models import Payment, User
from sqlalchemy import select
from utils.logging import get_logger, setup_logging

logger = get_logger(__name__)

PRO_DURATION_DAYS = 30


async def handle_yookassa_webhook(request: web.Request) -> web.Response:
    """
    Принимает webhook от YooKassa.

    Обязательно проверяем уникальность yookassa_payment_id — чтобы повторный
    webhook не выдал PRO дважды (см. ТЗ п.34).
    """
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"status": "bad_request"}, status=400)

    event = data.get("event")
    obj = data.get("object", {})
    payment_id = obj.get("id")
    status = obj.get("status")
    metadata = obj.get("metadata", {}) or {}
    user_id = metadata.get("user_id")

    logger.info(f"Webhook received: event={event} payment_id={payment_id} status={status}")

    if event != "payment.succeeded" or not payment_id:
        return web.json_response({"status": "ignored"})

    async with async_session() as session:
        payment = (
            await session.execute(
                select(Payment).where(Payment.yookassa_payment_id == payment_id)
            )
        ).scalar_one_or_none()

        if payment is None:
            logger.warning(f"Payment {payment_id} not found in DB")
            return web.json_response({"status": "not_found"}, status=404)

        # Защита от повторного webhook
        if payment.status == "succeeded":
            logger.info(f"Payment {payment_id} already processed")
            return web.json_response({"status": "already_processed"})

        payment.status = "succeeded"
        payment.paid_at = datetime.utcnow()

        # Выдаём PRO
        if user_id:
            user = (await session.execute(select(User).where(User.id == int(user_id)))).scalar_one_or_none()
            if user:
                now = datetime.utcnow()
                base = user.premium_until if (user.premium_until and user.premium_until > now) else now
                user.premium_until = base + timedelta(days=PRO_DURATION_DAYS)
                logger.info(f"PRO granted to user {user.id} until {user.premium_until}")

        await session.commit()

    return web.json_response({"status": "ok"})


async def handle_health(request: web.Request) -> web.Response:
    return web.json_response({"status": "healthy"})


def create_app() -> web.Application:
    app = web.Application()
    app.router.add_post("/yookassa/webhook", handle_yookassa_webhook)
    app.router.add_get("/health", handle_health)
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
    asyncio.run(run_server())