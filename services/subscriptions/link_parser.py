import re
from typing import Optional


# Паттерны для разных форм ссылок
_PATTERNS = [
    # https://t.me/username
    re.compile(r"^https?://t\.me/([A-Za-z0-9_]{5,64})/?$"),
    # t.me/username
    re.compile(r"^t\.me/([A-Za-z0-9_]{5,64})/?$"),
    # @username
    re.compile(r"^@([A-Za-z0-9_]{5,64})$"),
    # username (без @)
    re.compile(r"^([A-Za-z0-9_]{5,64})$"),
    # https://t.me/+invite_hash — приватные каналы по ссылке-приглашению
    re.compile(r"^https?://t\.me/\+([A-Za-z0-9_-]+)$"),
    # https://t.me/joinchat/hash — старый формат
    re.compile(r"^https?://t\.me/joinchat/([A-Za-z0-9_-]+)$"),
]


def parse_channel_link(text: str) -> Optional[dict]:
    """
    Разбирает ссылку/username канала.
    
    Возвращает:
    - {"type": "public", "username": "...", "link": "https://t.me/..."}
    - {"type": "private", "invite_hash": "...", "link": "..."}
    - None, если не распознано
    """
    text = text.strip()

    if not text:
        return None

    # 1. Публичный канал по username
    for pattern in _PATTERNS[:4]:
        match = pattern.match(text)
        if match:
            username = match.group(1)
            return {
                "type": "public",
                "username": username,
                "link": f"https://t.me/{username}",
            }

    # 2. Приватный по инвайт-хешу
    for pattern in _PATTERNS[4:]:
        match = pattern.match(text)
        if match:
            invite_hash = match.group(1)
            return {
                "type": "private",
                "invite_hash": invite_hash,
                "link": text if text.startswith("http") else f"https://{text}",
            }

    return None