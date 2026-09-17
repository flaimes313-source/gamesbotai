import hashlib
import random
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.connection import async_session
from database.models import ExperimentAssignment
from utils.logging import get_logger

logger = get_logger(__name__)


# Реестр экспериментов: имя → список версий
EXPERIMENTS = {
    "photo_prompt": ["photo_v1", "photo_v2"],
}


async def get_variant(
    experiment: str,
    telegram_id: int,
    session: Optional[AsyncSession] = None,
) -> str:
    """
    Возвращает вариант эксперимента для пользователя.
    Назначение стабильно сохраняется в БД — один и тот же пользователь
    всегда попадает в одну и ту же группу.
    """
    versions = EXPERIMENTS.get(experiment)
    if not versions:
        return "default"

    # Проверяем, назначен ли уже вариант
    own_session = session is None
    if own_session:
        session = async_session()

    try:
        row = (await session.execute(
            select(ExperimentAssignment).where(
                ExperimentAssignment.experiment == experiment,
                ExperimentAssignment.telegram_id == telegram_id,
            )
        )).scalar_one_or_none()

        if row:
            return row.variant

        # Назначаем: детерминированно по telegram_id, чтобы не дёргался при гонках
        h = int(hashlib.md5(f"{experiment}:{telegram_id}".encode()).hexdigest(), 16)
        variant = versions[h % len(versions)]

        session.add(ExperimentAssignment(
            experiment=experiment,
            telegram_id=telegram_id,
            variant=variant,
        ))
        await session.commit()
        logger.info(f"Experiment {experiment}: user={telegram_id} → {variant}")
        return variant

    finally:
        if own_session:
            await session.close()


def pick_prompt_by_variant(variant: str) -> tuple[str, str]:
    """
    Возвращает (prompt_text, prompt_version) для указанного варианта.
    """
    if variant == "photo_v2":
        from prompts.photo_analysis_v2 import PHOTO_ANALYSIS_PROMPT_V2
        return PHOTO_ANALYSIS_PROMPT_V2, "photo_v2"

    from prompts.photo_analysis import PHOTO_ANALYSIS_PROMPT
    return PHOTO_ANALYSIS_PROMPT, "photo_v1"