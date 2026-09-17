import os
import sys
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
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "").strip()
    ADMIN_IDS: List[int] = _get_int_list("ADMIN_IDS")

    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "").strip()

    # GigaChat
    GIGACHAT_API_KEY: str = os.getenv("GIGACHAT_API_KEY", "").strip()
    GIGACHAT_SCOPE: str = os.getenv("GIGACHAT_SCOPE", "GIGACHAT_API_PERS").strip()
    GIGACHAT_MODEL: str = os.getenv("GIGACHAT_MODEL", "GigaChat-2").strip()

    # YandexGPT (опционально)
    YANDEX_FOLDER_ID: str = os.getenv("YANDEX_FOLDER_ID", "").strip()
    YANDEX_API_KEY: str = os.getenv("YANDEX_API_KEY", "").strip()
    YANDEX_MODEL: str = os.getenv("YANDEX_MODEL", "yandexgpt-lite").strip()

    # Feature flags
    MANDATORY_SUBSCRIPTIONS: bool = _get_bool("MANDATORY_SUBSCRIPTIONS")
    ADVERTISING_ENABLED: bool = _get_bool("ADVERTISING_ENABLED")
    PREMIUM_ENABLED: bool = _get_bool("PREMIUM_ENABLED")
    MATCHING_ENABLED: bool = _get_bool("MATCHING_ENABLED", True)
    REFERRALS_ENABLED: bool = _get_bool("REFERRALS_ENABLED", True)

    # YooKassa
    YOOKASSA_SHOP_ID: str = os.getenv("YOOKASSA_SHOP_ID", "").strip()
    YOOKASSA_SECRET: str = os.getenv("YOOKASSA_SECRET", "").strip()

    # Paths
    LOGS_DIR: str = "logs"
    DATA_DIR: str = "data"
    PROMPT_VERSION_PHOTO: str = "photo_v1"

    # Debug
    DEBUG: bool = _get_bool("DEBUG", False)


config = Config()


def _validate_config() -> None:
    errors: List[str] = []

    if not config.BOT_TOKEN:
        errors.append("BOT_TOKEN is empty.")
    if not config.DATABASE_URL:
        errors.append("DATABASE_URL is empty.")
    if not config.GIGACHAT_API_KEY:
        errors.append("GIGACHAT_API_KEY is empty.")

    if errors:
        print("=" * 60, file=sys.stderr)
        print("CONFIGURATION ERROR", file=sys.stderr)
        print("=" * 60, file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        print("=" * 60, file=sys.stderr)
        sys.exit(1)


_validate_config()