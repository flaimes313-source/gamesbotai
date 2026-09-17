from typing import Any, Dict

NUMERIC_KEYS = [
    "charisma",
    "confidence",
    "humor",
    "energy",
    "sociability",
    "intellect",
    "creativity",
    "calmness",
    "chaos",
    "leadership",
]


def clamp_scores(data: Dict[str, Any]) -> Dict[str, Any]:
    """Приводим все оценки к 0..100."""
    scores = data.get("scores") or {}
    for key in NUMERIC_KEYS:
        value = scores.get(key, 0)
        try:
            value = int(value)
        except (TypeError, ValueError):
            value = 0
        scores[key] = max(0, min(100, value))

    data["scores"] = scores

    for key in ("danger_level", "friendship_score"):
        try:
            data[key] = max(0, min(100, int(data.get(key, 0))))
        except (TypeError, ValueError):
            data[key] = 0

    return data