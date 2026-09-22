import hashlib
import random
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.connection import async_session
from database.models import ExperimentAssignment
from utils.logging import get_logger

logger = get_logger(__name__)


# ============================================================
# Реестр экспериментов: имя → список версий
#
# photo_prompt:
#   - photo_v1 — базовый промт (короткий, без деталей).
#   - photo_v2 — расширенный, с деталями и дерзким стилем.
#   - photo_v3 — эпичные названия архетипов + явный запрет
#                генерить «легендарные» имена (за них
#                отвечает бэк, см. services/analysis/rarity.py).
#
# ВАЖНО:
#   - Назначение варианта СТАБИЛЬНО на telegram_id (md5).
#   - Уже назначенные юзеры НЕ переезжают при изменении списка.
#   - Новые юзеры распределяются по всем трём вариантам.
#   - Чтобы «схлопнуть» до одного — просто удали лишние
#     из списка ниже (старые останутся в БД, но новые
#     анализы пойдут только по актуальным).
# ============================================================
EXPERIMENTS = {
    "photo_prompt": ["photo_v1", "photo_v2", "photo_v3"],
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

    Если вариант устарел (его больше нет в EXPERIMENTS, но
    он сохранён в БД у старого юзера) — отдаём v3 как
    актуальный дефолт. Это защищает от KeyError и от
    ситуации, когда юзер «завис» на удалённой ветке.
    """
    if variant == "photo_v3":
        from prompts.photo_analysis_v3 import PHOTO_ANALYSIS_PROMPT_V3
        return PHOTO_ANALYSIS_PROMPT_V3, "photo_v3"

    if variant == "photo_v2":
        from prompts.photo_analysis_v2 import PHOTO_ANALYSIS_PROMPT_V2
        return PHOTO_ANALYSIS_PROMPT_V2, "photo_v2"

    if variant == "photo_v1":
        from prompts.photo_analysis import PHOTO_ANALYSIS_PROMPT
        return PHOTO_ANALYSIS_PROMPT, "photo_v1"

    # Неизвестный/устаревший вариант → актуальный дефолт
    logger.warning(f"Unknown prompt variant '{variant}', fallback to photo_v3")
    from prompts.photo_analysis_v3 import PHOTO_ANALYSIS_PROMPT_V3
    return PHOTO_ANALYSIS_PROMPT_V3, "photo_v3"