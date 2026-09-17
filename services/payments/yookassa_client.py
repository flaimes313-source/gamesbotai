from yookassa import Configuration, Payment
from config import config
from utils.logging import get_logger

logger = get_logger(__name__)


def init_yookassa() -> None:
    Configuration.account_id = config.YOOKASSA_SHOP_ID
    Configuration.secret_key = config.YOOKASSA_SECRET


def create_pro_payment(user_id: int, amount: float = 299.0) -> dict:
    init_yookassa()
    payment = Payment.create({
        "amount": {"value": f"{amount:.2f}", "currency": "RUB"},
        "confirmation": {"type": "redirect", "return_url": "https://t.me/"},
        "capture": True,
        "description": f"PRO подписка для пользователя {user_id}",
        "metadata": {"user_id": user_id, "type": "pro"},
    })
    return {"id": payment.id, "confirmation_url": payment.confirmation.confirmation_url}