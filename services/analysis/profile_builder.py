from typing import Any, Dict

from database.models import Profile
from services.analysis.scoring import clamp_scores


def build_profile(user_id: int, analysis: Dict[str, Any]) -> Profile:
    data = clamp_scores(dict(analysis))
    scores = data.get("scores", {})

    profile = Profile(
        user_id=user_id,
        archetype=str(data.get("archetype", "ЗАГАДОЧНЫЙ ТИП"))[:128],
        description=str(data.get("short_description", "")),
        charisma=scores.get("charisma", 0),
        confidence=scores.get("confidence", 0),
        humor=scores.get("humor", 0),
        energy=scores.get("energy", 0),
        sociability=scores.get("sociability", 0),
        intellect=scores.get("intellect", 0),
        creativity=scores.get("creativity", 0),
        calmness=scores.get("calmness", 0),
        chaos=scores.get("chaos", 0),
        leadership=scores.get("leadership", 0),
        funny_trait=str(data.get("funny_trait", ""))[:512],
        danger_level=int(data.get("danger_level", 0)),
        friendship_score=int(data.get("friendship_score", 0)),
        vibe=str(data.get("vibe", ""))[:256],
    )
    return profile