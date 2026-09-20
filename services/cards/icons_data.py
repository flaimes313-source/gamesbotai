"""
Автоматически сгенерированный файл. НЕ редактировать вручную.

PNG-иконки для карточек, вшитые в base64.
Сгенерировано: tools/build_embedded_icons.py
"""

import base64

STAT_CHARISMA_PNG = (
    "NDA0OiBOb3QgRm91bmQ="
)

STAT_HUMOR_PNG = (
    "NDA0OiBOb3QgRm91bmQ="
)

STAT_CHAOS_PNG = (
    "NDA0OiBOb3QgRm91bmQ="
)

STAT_INTELLECT_PNG = (
    "NDA0OiBOb3QgRm91bmQ="
)

STAT_ENERGY_PNG = (
    "NDA0OiBOb3QgRm91bmQ="
)

STAT_CREATIVITY_PNG = (
    "NDA0OiBOb3QgRm91bmQ="
)

ACH_FIRST_PHOTO_PNG = (
    "NDA0OiBOb3QgRm91bmQ="
)

ACH_FIRST_SHARE_PNG = (
    "NDA0OiBOb3QgRm91bmQ="
)

ACH_FRIEND_JOINED_PNG = (
    "NDA0OiBOb3QgRm91bmQ="
)

ACH_FIRST_TEST_PNG = (
    "NDA0OiBOb3QgRm91bmQ="
)

ACH_FIVE_TESTS_PNG = (
    "NDA0OiBOb3QgRm91bmQ="
)

ACH_CHAOS_90_PNG = (
    "NDA0OiBOb3QgRm91bmQ="
)

ACH_CHARISMA_90_PNG = (
    "NDA0OiBOb3QgRm91bmQ="
)

ACH_FIVE_ANALYSES_PNG = (
    "NDA0OiBOb3QgRm91bmQ="
)

ACH_FIRST_MATCH_PNG = (
    "NDA0OiBOb3QgRm91bmQ="
)

ACH_TEN_MESSAGES_PNG = (
    "NDA0OiBOb3QgRm91bmQ="
)

ACH_PRO_FIRST_PNG = (
    "NDA0OiBOb3QgRm91bmQ="
)

ACH_DEFAULT_PNG = (
    "NDA0OiBOb3QgRm91bmQ="
)


def get_icon_bytes(name: str) -> bytes | None:
    """Возвращает байты иконки по ключу."""
    value = globals().get(name)
    if value is None:
        return None
    return base64.b64decode(value)
