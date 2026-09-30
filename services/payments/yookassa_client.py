"""
Клиент YooKassa для создания платежей PRO.

ВАЖНО: SDK YooKassa синхронный. Все вызовы оборачиваем в asyncio.to_thread,
чтобы не блокировать event loop бота.
"""

import asyncio
from typing import Optional

from yookassa import Configuration, Payment

from config import config
from utils.logging import get_logger

logger = get_logger(__name__)


# ============================================================
# ИНИЦИАЛИЗАЦИЯ
# ============================================================
def _init() -> None:
    """Инициализация SDK. Безопасно вызывать многократно."""
    Configuration.account_id = config.YOOKASSA_SHOP_ID
    Configuration.secret_key = config.YOOKASSA_SECRET


# ============================================================
# СОЗДАНИЕ ПЛАТЕЖА PRO
# ============================================================
async def create_pro_payment(
    user_id: int,
    amount: float = 390.0,
    description: str = "PRO подписка",
    months: int = 1,
    bot_username: Optional[str] = None,
) -> dict:
    """
    Создаёт платёж PRO в YooKassa.

    Параметры:
        user_id — внутренний id юзера в БД (для metadata).
        amount — сумма в рублях.
        description — описание (видно юзеру).
        months — на сколько месяцев (для metadata).
        bot_username — username бота (для return_url).

    Возвращает:
        {
            "id": str,
            "confirmation_url": str,
            "status": str,
        }

    ВАЖНО:
    - save_payment_method=True — на будущее для автопродления.
    - metadata.user_id — webhook по нему найдёт юзера.
    """
    _init()

    # Куда вернуть юзера после оплаты
    if bot_username:
        return_url = f"https://t.me/{bot_username}"
    else:
        return_url = "https://t.me/"

    payload = {
        "amount": {"value": f"{amount:.2f}", "currency": "RUB"},
        "confirmation": {
            "type": "redirect",
            "return_url": return_url,
        },
        "capture": True,
        "save_payment_method": True,
        "description": description,
        "metadata": {
            "user_id": user_id,
            "type": "pro",
            "months": months,
        },
    }

    def _create():
        return Payment.create(payload)

    try:
        payment = await asyncio.to_thread(_create)
    except Exception:
        logger.exception("[YOOKASSA] Payment.create failed")
        raise

    result = {
        "id": payment.id,
        "confirmation_url": payment.confirmation.confirmation_url,
        "status": payment.status,
    }

    logger.info(
        f"[YOOKASSA] payment created id={payment.id} "
        f"user={user_id} amount={amount} months={months}"
    )
    return result


# ============================================================
# ПОЛУЧЕНИЕ СТАТУСА (для поллинга / отладки)
# ============================================================
async def get_payment_status(payment_id: str) -> Optional[dict]:
    """
    Возвращает статус платежа из YooKassa.
    Полезно для отладки, если webhook не приходит.
    """
    _init()

    def _get():
        return Payment.find_one(payment_id)

    try:
        payment = await asyncio.to_thread(_get)
    except Exception:
        logger.exception(f"[YOOKASSA] find_one failed id={payment_id}")
        return None

    if payment is None:
        return None

    return {
        "id": payment.id,
        "status": payment.status,
        "paid": payment.paid,
        "amount": payment.amount.value if payment.amount else None,
        "metadata": payment.metadata or {},
    }