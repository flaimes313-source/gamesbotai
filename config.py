import os
from typing import List
from dotenv import load_dotenv

load_dotenv()


def _get_bool(key: str, default: bool = False) -> bool:
    value = os.getenv(key, str(default)).lower()
    return value in ("1", "true", "yes", "on")


def _get_int_list(key: str) -> List[int]:
    raw = os.getenv(key, "").strip()
    if not raw:
        return []
    return [int(x.strip()) for x in raw.split(",") if x.strip()]


class Config:
    # Telegram
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
    ADMIN_IDS: List[int] = _get_int_list("ADMIN_IDS")

    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "")

    # GigaChat
    GIGACHAT_API_KEY: str = os.getenv("GIGACHAT_API_KEY", "")
    GIGACHAT_SCOPE: str = os.getenv("GIGACHAT_SCOPE", "GIGACHAT_API_PERS")
    GIGACHAT_MODEL: str = os.getenv("GIGACHAT_MODEL", "GigaChat-2")

    # Feature flags
    MANDATORY_SUBSCRIPTIONS: bool = _get_bool("MANDATORY_SUBSCRIPTIONS")
    ADVERTISING_ENABLED: bool = _get_bool("ADVERTISING_ENABLED")
    PREMIUM_ENABLED: bool = _get_bool("PREMIUM_ENABLED")
    MATCHING_ENABLED: bool = _get_bool("MATCHING_ENABLED", True)
    REFERRALS_ENABLED: bool = _get_bool("REFERRALS_ENABLED", True)

    # YooKassa (опционально, для этапа 5)
    YOOKASSA_SHOP_ID: str = os.getenv("YOOKASSA_SHOP_ID", "")
    YOOKASSA_SECRET: str = os.getenv("YOOKASSA_SECRET", "")

    # Paths
    LOGS_DIR: str = "logs"
    DATA_DIR: str = "data"
    PROMPT_VERSION_PHOTO: str = "photo_v1"


config = Config()