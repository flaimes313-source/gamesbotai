from sqlalchemy import select

from database.connection import async_session
from database.models import FeatureFlag
from utils.logging import get_logger

logger = get_logger(__name__)

# Кэш в памяти: обновляется раз в N секунд, чтобы не бить БД на каждый вызов
_cache: dict[str, bool] = {}
_cache_loaded: bool = False


# Дефолтные значения — если флага нет в БД
DEFAULTS: dict[str, bool] = {
    "bot_enabled": True,
    "ai_enabled": True,
    "matching_enabled": True,
    "referrals_enabled": True,
    "mandatory_subscriptions_enabled": False,
    "advertising_enabled": False,
    "premium_enabled": False,
    "daily_content_enabled": False,
    "friend_comparison_enabled": True,
    "player_search_enabled": True,
    "ai_message_helper_enabled": True,
}


async def is_enabled(key: str, default: bool | None = None) -> bool:
    """
    Проверяет флаг:
    - сначала ищет в БД,
    - если нет — возвращает дефолт из DEFAULTS или переданный default.
    """
    async with async_session() as session:
        flag = (await session.execute(
            select(FeatureFlag).where(FeatureFlag.key == key)
        )).scalar_one_or_none()

    if flag is not None:
        return flag.enabled

    if default is not None:
        return default

    return DEFAULTS.get(key, False)


async def set_flag(key: str, enabled: bool) -> None:
    """Устанавливает значение флага."""
    async with async_session() as session:
        flag = (await session.execute(
            select(FeatureFlag).where(FeatureFlag.key == key)
        )).scalar_one_or_none()

        if flag:
            flag.enabled = enabled
        else:
            session.add(FeatureFlag(key=key, enabled=enabled))

        await session.commit()
        logger.info(f"Flag {key} = {enabled}")


async def get_all_flags() -> dict[str, bool]:
    """Возвращает все флаги с дефолтами."""
    async with async_session() as session:
        rows = (await session.execute(select(FeatureFlag))).scalars().all()

    flags = dict(DEFAULTS)
    for r in rows:
        flags[r.key] = r.enabled
    return flags


async def ensure_flags_exist() -> None:
    """
    Создаёт в БД все дефолтные флаги, если их нет.
    Вызывается при старте бота.
    """
    async with async_session() as session:
        existing = {
            r.key for r in (await session.execute(select(FeatureFlag))).scalars().all()
        }

        added = 0
        for key, value in DEFAULTS.items():
            if key not in existing:
                session.add(FeatureFlag(key=key, enabled=value))
                added += 1

        if added:
            await session.commit()
            logger.info(f"Feature flags: created {added} defaults")