import json
import random
from pathlib import Path

JOKES_PATH = Path("data/jokes.json")
_cache: dict | None = None


def _load() -> dict:
    global _cache
    if _cache is None:
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