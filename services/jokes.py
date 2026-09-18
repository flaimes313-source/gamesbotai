import json
import random
from pathlib import Path

# Корень проекта: services/jokes.py → services/ → корень
PROJECT_ROOT = Path(__file__).resolve().parent.parent
JOKES_PATH = PROJECT_ROOT / "data" / "jokes.json"

_cache: dict | None = None


def _load() -> dict:
    global _cache
    if _cache is None:
        if not JOKES_PATH.exists():
            raise FileNotFoundError(f"Jokes file not found: {JOKES_PATH}")
        _cache = json.loads(JOKES_PATH.read_text(encoding="utf-8"))
    return _cache


def random_joke(category: str | None = None) -> str:
    data = _load()

    if category and category in data:
        return random.choice(data[category])

    all_jokes = [j for jokes in data.values() for j in jokes]
    return random.choice(all_jokes) if all_jokes else "😂"


def categories() -> list[str]:
    return list(_load().keys())