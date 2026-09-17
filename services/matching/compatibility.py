from typing import Any, Dict

# Веса для расчёта совместимости (кому какие черты важны в балансе)
WEIGHTS = {
    "humor": 1.4,
    "energy": 1.1,
    "chaos": 0.8,
    "intellect": 1.0,
    "charisma": 1.2,
    "sociability": 1.0,
    "creativity": 1.1,
    "calmness": 0.7,
    "confidence": 1.0,
    "leadership": 0.8,
}


def _diff_based_score(a: int, b: int) -> float:
    """Чем ближе значения, тем выше очки (0..100)."""
    return 100.0 - abs(a - b)


def compatibility_score(p1: Dict[str, Any], p2: Dict[str, Any]) -> int:
    total = 0.0
    total_weight = 0.0
    for key, weight in WEIGHTS.items():
        a = int(p1.get(key, 0))
        b = int(p2.get(key, 0))
        total += _diff_based_score(a, b) * weight
        total_weight += weight
    if total_weight == 0:
        return 0
    return int(round(total / total_weight))