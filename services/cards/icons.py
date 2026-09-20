"""
Загрузка PNG-иконок для карточек.
Кэширует иконки в памяти, чтобы не читать диск каждый раз.
"""
import os
from pathlib import Path
from typing import Optional

from PIL import Image

from utils.logging import get_logger

logger = get_logger(__name__)


# Корень проекта → data/icons/
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_ICONS_DIR = _PROJECT_ROOT / "data" / "icons"

# Кэш: имя → PIL.Image
_cache: dict[str, Image.Image] = {}


# ============================================================
# Соответствия: код → имя файла
# ============================================================
STAT_ICONS = {
    "charisma": "stat_charisma.png",
    "humor": "stat_humor.png",
    "chaos": "stat_chaos.png",
    "intellect": "stat_intellect.png",
    "energy": "stat_energy.png",
    "creativity": "stat_creativity.png",
}

ACHIEVEMENT_ICONS = {
    "first_photo": "ach_first_photo.png",
    "first_share": "ach_first_share.png",
    "friend_joined": "ach_friend_joined.png",
    "first_test": "ach_first_test.png",
    "five_tests": "ach_five_tests.png",
    "chaos_90": "ach_chaos_90.png",
    "charisma_90": "ach_charisma_90.png",
    "five_analyses": "ach_five_analyses.png",
    "first_match": "ach_first_match.png",
    "ten_messages": "ach_ten_messages.png",
    "pro_first": "ach_pro_first.png",
}

DEFAULT_ACHIEVEMENT_ICON = "ach_default.png"


# ============================================================
# Загрузка
# ============================================================
def load_icon(filename: str, size: int = 48) -> Optional[Image.Image]:
    """
    Загружает PNG-иконку по имени файла.
    Возвращает RGBA-изображение нужного размера или None.
    """
    cache_key = f"{filename}:{size}"
    if cache_key in _cache:
        return _cache[cache_key]

    path = _ICONS_DIR / filename
    if not path.exists():
        logger.warning(f"[ICONS] Not found: {path}")
        return None

    try:
        img = Image.open(path).convert("RGBA")
        img = img.resize((size, size), Image.LANCZOS)
        _cache[cache_key] = img
        return img
    except Exception:
        logger.exception(f"[ICONS] Failed to load {path}")
        return None


def stat_icon(key: str, size: int = 40) -> Optional[Image.Image]:
    """Иконка для характеристики."""
    filename = STAT_ICONS.get(key)
    if not filename:
        return None
    return load_icon(filename, size=size)


def achievement_icon(code: str, size: int = 32) -> Optional[Image.Image]:
    """Иконка для достижения."""
    filename = ACHIEVEMENT_ICONS.get(code)
    if not filename:
        filename = DEFAULT_ACHIEVEMENT_ICON
    return load_icon(filename, size=size)


def icons_available() -> bool:
    """Проверяет, что папка с иконками существует."""
    return _ICONS_DIR.exists()