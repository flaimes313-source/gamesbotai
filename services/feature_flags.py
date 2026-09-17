from sqlalchemy import select
from database.connection import async_session
from database.models import FeatureFlag
from utils.logging import get_logger

logger = get_logger(__name__)


async def is_enabled(key: str, default: bool = False) -> bool:
    async with async_session() as session:
        flag = (await session.execute(select(FeatureFlag).where(FeatureFlag.key == key))).scalar_one_or_none()
        return flag.enabled if flag else default


async def set_flag(key: str, enabled: bool) -> None:
    async with async_session() as session:
        flag = (await session.execute(select(FeatureFlag).where(FeatureFlag.key == key))).scalar_one_or_none()
        if flag:
            flag.enabled = enabled
        else:
            session.add(FeatureFlag(key=key, enabled=enabled))
        await session.commit()
        logger.info(f"Flag {key} = {enabled}")