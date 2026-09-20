"""
Загрузка PNG-иконок для карточек.
Иконки вшиты в base64 (services/cards/icons_data.py) —
не зависят от файловой системы, работают на любом хостинге.

Совместимо с Python 3.9+.
"""
import io
from typing import Optional

from PIL import Image

from services.cards.icons_data import get_icon_bytes
from utils.logging import get_logger

logger = get_logger(__name__)


# Кэш: (key, size) → PIL.Image
_cache: dict = {}


# ============================================================
# Соответствия: ключ → имя переменной в icons_data.py
# ============================================================
STAT_ICONS = {
    "charisma": "STAT_CHARISMA_PNG",
    "humor": "STAT_HUMOR_PNG",
    "chaos": "STAT_CHAOS_PNG",
    "intellect": "STAT_INTELLECT_PNG",
    "energy": "STAT_ENERGY_PNG",
    "creativity": "STAT_CREATIVITY_PNG",
}

ACHIEVEMENT_ICONS = {
    "first_photo": "ACH_FIRST_PHOTO_PNG",
    "first_share": "ACH_FIRST_SHARE_PNG",
    "friend_joined": "ACH_FRIEND_JOINED_PNG",
    "first_test": "ACH_FIRST_TEST_PNG",
    "five_tests": "ACH_FIVE_TESTS_PNG",
    "chaos_90": "ACH_CHAOS_90_PNG",
    "charisma_90": "ACH_CHARISMA_90_PNG",
    "five_analyses": "ACH_FIVE_ANALYSES_PNG",
    "first_match": "ACH_FIRST_MATCH_PNG",
    "ten_messages": "ACH_TEN_MESSAGES_PNG",
    "pro_first": "ACH_PRO_FIRST_PNG",
}

DEFAULT_ACHIEVEMENT_ICON = "ACH_DEFAULT_PNG"


# ============================================================
# Загрузка
# ============================================================
def _load_png(key: str, size: int = 48) -> Optional[Image.Image]:
    """
    Загружает PNG по имени переменной в icons_data.py.
    Ресайзит до size × size.
    """
    cache_key = (key, size)
    if cache_key in _cache:
        return _cache[cache_key]

    try:
        data = get_icon_bytes(key)
        if data is None:
            logger.warning(f"[ICONS] No data for key: {key}")
            return None

        img = Image.open(io.BytesIO(data)).convert("RGBA")
        img = img.resize((size, size), Image.LANCZOS)
        _cache[cache_key] = img
        return img
    except Exception:
        logger.exception(f"[ICONS] Failed to load {key}")
        return None


def stat_icon(key: str, size: int = 40) -> Optional[Image.Image]:
    """Иконка для характеристики."""
    var_name = STAT_ICONS.get(key)
    if not var_name:
        return None
    return _load_png(var_name, size=size)


def achievement_icon(code: str, size: int = 32) -> Optional[Image.Image]:
    """Иконка для достижения."""
    var_name = ACHIEVEMENT_ICONS.get(code)
    if not var_name:
        var_name = DEFAULT_ACHIEVEMENT_ICON
    return _load_png(var_name, size=size)


# ============================================================
# Диагностика при импорте
# ============================================================
logger.info("[ICONS] icons.py loaded (base64 mode)")


def _diagnose() -> None:
    """Проверяет, что все иконки доступны."""
    try:
        missing = []
        for key in STAT_ICONS.values():
            if get_icon_bytes(key) is None:
                missing.append(key)
        for key in ACHIEVEMENT_ICONS.values():
            if get_icon_bytes(key) is None:
                missing.append(key)
        if get_icon_bytes(DEFAULT_ACHIEVEMENT_ICON) is None:
            missing.append(DEFAULT_ACHIEVEMENT_ICON)

        if missing:
            logger.warning(f"[ICONS] Missing icons: {missing}")
        else:
            logger.info("[ICONS] All icons loaded OK")
    except Exception:
        logger.exception("[ICONS] Diagnosis failed")


_diagnose()