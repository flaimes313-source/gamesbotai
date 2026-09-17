from aiohttp import web

async def yookassa_webhook(request: web.Request) -> web.Response:
    data = await request.json()
    event = data.get("event")
    obj = data.get("object", {})
    payment_id = obj.get("id")
    status = obj.get("status")
    if event == "payment.succeeded" and payment_id:
        # здесь обновляем Payment → succeeded, выдаём PRO
        ...
    return web.Response(status=200)