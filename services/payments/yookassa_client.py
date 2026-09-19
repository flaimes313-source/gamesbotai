from yookassa import Configuration, Payment

from config import config
from utils.logging import get_logger

logger = get_logger(__name__)


def init_yookassa() -> None:
    Configuration.account_id = config.YOOKASSA_SHOP_ID
    Configuration.secret_key = config.YOOKASSA_SECRET


def create_pro_payment(
    user_id: int,
    amount: float = 390.0,
    description: str = "PRO подписка",
    months: int = 1,
) -> dict:
    """
    Создаёт платёж PRO.
    Автопродление: save_payment_method=True, чтобы потом можно было
    списывать повторно без участия юзера.
    """
    init_yookassa()

    payment = Payment.create({
        "amount": {"value": f"{amount:.2f}", "currency": "RUB"},
        "confirmation": {
            "type": "redirect",
            "return_url": "https://t.me/",
        },
        "capture": True,
        "save_payment_method": True,
        "description": description,
        "metadata": {
            "user_id": user_id,
            "type": "pro",
            "months": months,
        },
    })

    return {
        "id": payment.id,
        "confirmation_url": payment.confirmation.confirmation_url,
        "payment_method_id": getattr(payment, "payment_method", {}).get("id") if hasattr(payment, "payment_method") else None,
    }