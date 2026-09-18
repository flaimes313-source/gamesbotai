from config import config
from services.premium import is_premium
from services.whitelist import is_whitelisted


async def has_full_access(telegram_id: int) -> bool:
    """
    True если пользователь имеет полный доступ:
    - администратор
    - в whitelist
    - PRO-подписчик
    """
    if telegram_id in config.ADMIN_IDS:
        return True

    if await is_whitelisted(telegram_id):
        return True

    if await is_premium(telegram_id):
        return True

    return False


async def access_level(telegram_id: int) -> str:
    """
    Возвращает уровень доступа:
    - "admin"
    - "whitelist"
    - "pro"
    - "free"
    """
    if telegram_id in config.ADMIN_IDS:
        return "admin"

    if await is_whitelisted(telegram_id):
        return "whitelist"

    if await is_premium(telegram_id):
        return "pro"

    return "free"