"""
Секретная фича дня (Этап 2).

Логика:
- Юзера не было 2+ дня → шлём ему одну подсказку про фичу.
- Ротация: одна и та же подсказка не повторяется (RewardClaim).
- Отправка через hub (kind="secret_feature", priority=4).

Не пушит активным — только «отсутствующим».

ВАЖНО: FEATURE_TIPS встроен прямо в этот модуль (не в data/),
чтобы не зависеть от .gitignore и структуры папок на BotHost.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select

from database.connection import async_session
from database.models import RewardClaim
from utils.logging import get_logger

logger = get_logger(__name__)


# ============================================================
# КОНСТАНТЫ
# ============================================================
MIN_DAYS_AWAY = 2                 # не был 2+ дня
MAX_DAYS_AWAY = 60                # если пропал больше 2 месяцев — не спамим
REWARD_PREFIX = "tip_seen_"       # префикс RewardClaim для виденных подсказок


# ============================================================
# ПОДСКАЗКИ (30 штук)
# ============================================================
FEATURE_TIPS: List[Dict[str, str]] = [
    # === Чаты и общение ===
    {
        "code": "chat_jokes",
        "emoji": "🎭",
        "text": "В чате с другом можно отправить <b>прикол</b> — кнопка 🎭 под полем ввода. Идеально, когда не знаешь, что сказать.",
    },
    {
        "code": "chat_ai_helper",
        "emoji": "🤖",
        "text": "С PRO в чате работает <b>AI-помощник</b>: 3 варианта ответа и анализ переписки. Кнопка 🤖 в чате.",
    },
    {
        "code": "chat_message_styles",
        "emoji": "✍️",
        "text": "Перед отправкой сообщения можно выбрать <b>стиль</b> — дерзкий, тёплый, шутливый. Смотри настройки в чате.",
    },

    # === Профиль и карточки ===
    {
        "code": "dynamics",
        "emoji": "📈",
        "text": "Хочешь увидеть, как менялся твой вайб? <b>👤 Мой профиль → 📈 Моя динамика</b> — там график роста.",
    },
    {
        "code": "vibe_report",
        "emoji": "🧠",
        "text": "AI может написать <b>психологический портрет</b> твоего вайба. <b>👤 Мой профиль → 🧠 Мой вайб-отчёт</b>.",
    },
    {
        "code": "legendary_hunt",
        "emoji": "✨",
        "text": "Иногда выпадает <b>ЛЕГЕНДАРНЫЙ архетип</b> — с золотой рамкой. Шанс 3% за анализ. Лови!",
    },
    {
        "code": "share_forward",
        "emoji": "📤",
        "text": "Свою карточку можно <b>переслать другу</b> прямо в Telegram — нажми на неё и удерживай.",
    },

    # === Друзья и рефералка ===
    {
        "code": "referral_pro",
        "emoji": "🎁",
        "text": "Пригласи <b>10 друзей</b> — получишь <b>7 дней PRO бесплатно</b>. Прогресс в 📊 Моя статистика.",
    },
    {
        "code": "compare_friend",
        "emoji": "👥",
        "text": "Можно <b>сравнить вайб с другом</b>: <b>👥 Сравнить</b> в меню. Покажет совместимость в %.",
    },
    {
        "code": "referral_30_days",
        "emoji": "⏳",
        "text": "Рефералы считаются только за <b>последние 30 дней</b>. Если друг зашёл давно — он не в счёт.",
    },

    # === Игра и поиск ===
    {
        "code": "matching_modes",
        "emoji": "🎯",
        "text": "В поиске игроков есть <b>7 режимов</b> — от «похожих на тебя» до «полная противоположность». Пробуй разные.",
    },
    {
        "code": "matching_pro_modes",
        "emoji": "🚀",
        "text": "С PRO открываются режимы <b>«Интеллектуальный»</b> и <b>«Максимальный хаос»</b>. Кнопка 🎯 Найти игроков.",
    },
    {
        "code": "game_opt_in",
        "emoji": "🎮",
        "text": "Чтобы тебя находили другие — включи <b>Социальную игру</b> в ⚙️ Настройках.",
    },

    # === Тесты ===
    {
        "code": "tests_list",
        "emoji": "🧪",
        "text": "В боте <b>10 тестов</b>: от «Кто ты в хаосе» до «Твой стиль общения». <b>👤 Мой профиль → 🧪 Пройти тест</b>.",
    },
    {
        "code": "tests_achievements",
        "emoji": "🎓",
        "text": "За каждый тест дают <b>достижения</b> и очки. 5 тестов → достижение «🎓». Смотри 🏆 Достижения.",
    },

    # === Очки и уровни ===
    {
        "code": "points_from_challenges",
        "emoji": "🎯",
        "text": "За <b>челлендж дня</b> дают +50 очков. Каждый день новый. <b>🎯 Челлендж дня</b> в меню.",
    },
    {
        "code": "points_from_streak",
        "emoji": "🔥",
        "text": "Заходи каждый день — растёт <b>стрик</b>. За 7 дней подряд дают <b>1 день PRO</b>.",
    },
    {
        "code": "points_from_karma",
        "emoji": "🎁",
        "text": "При каждом заходе выпадает <b>карма дня</b> — от +10 до +100 очков. Просто зайди!",
    },
    {
        "code": "level_titles",
        "emoji": "🏅",
        "text": "В боте <b>20 уровней</b>: от «Новичка» до «ЛЕГЕНДЫ ВАЙБМИ». Свой уровень смотри в 📊 Моя статистика.",
    },

    # === Достижения ===
    {
        "code": "achievements_chaos",
        "emoji": "🧨",
        "text": "Есть достижение <b>«Хаос 90+»</b> — если анализ выдал тебе хаос выше 90. Повезёт — получишь.",
    },
    {
        "code": "achievements_legendary",
        "emoji": "✨",
        "text": "За <b>первый легендарный архетип</b> дают отдельное достижение. А за 5 разных — «🌟 Коллекционер легенд».",
    },

    # === PRO ===
    {
        "code": "pro_50_analyses",
        "emoji": "💎",
        "text": "С PRO можно делать <b>50 анализов в день</b> вместо 1. Полезно, если хочешь поймать легендарку.",
    },
    {
        "code": "pro_free_streak",
        "emoji": "🔥",
        "text": "PRO можно получить <b>бесплатно за стрик</b>: 7 дней подряд → 1 день PRO. Смотри ℹ️ О боте.",
    },
    {
        "code": "pro_free_points",
        "emoji": "⭐",
        "text": "PRO дают за <b>очки</b>: 1500 очков → 3 дня PRO. Смотри ℹ️ О боте → 💎 Как получить PRO.",
    },

    # === Приватность ===
    {
        "code": "privacy_username",
        "emoji": "🔒",
        "text": "Можно <b>скрыть username</b> от других игроков: ⚙️ Настройки → ⚙️ Приватность.",
    },
    {
        "code": "privacy_photo",
        "emoji": "📸",
        "text": "Фото, которые ты отправляешь, <b>никому не показываются</b>. Только твой архетип.",
    },

    # === Полезное ===
    {
        "code": "timezone",
        "emoji": "🌍",
        "text": "Настрой <b>часовой пояс</b> — и уведомления будут приходить в удобное время, а не ночью. ⚙️ Настройки → 🌍 Часовой пояс.",
    },
    {
        "code": "notifications_toggle",
        "emoji": "🔔",
        "text": "Не хочешь какие-то уведомления? <b>⚙️ Настройки → 🔔 Уведомления</b> — 7 тумблеров.",
    },
    {
        "code": "support",
        "emoji": "🆘",
        "text": "Если что-то не работает — <b>🆘 Поддержка</b> в меню. Отвечаем быстро.",
    },
    {
        "code": "blocking",
        "emoji": "🚫",
        "text": "Если кто-то в чате неприятен — можно <b>заблокировать</b>. Кнопка в чате с ним.",
    },

    # === Сезоны ===
    {
        "code": "seasons",
        "emoji": "🎉",
        "text": "В праздники AI выдаёт <b>сезонные архетипы</b> — например, новогодние. Следи за обновлениями!",
    },

    # === Приколы ===
    {
        "code": "daily_result",
        "emoji": "😂",
        "text": "Каждый день в 20:00 приходит <b>персональный прикол</b> про твой вайб. Не отключай — весело!",
    },
    {
        "code": "inline_share",
        "emoji": "📋",
        "text": "Ссылку на бота можно <b>скопировать</b> одной кнопкой: <b>📤 Поделиться → 📋 Скопировать ссылку</b>.",
    },
]


def all_tip_codes() -> List[str]:
    """Список всех кодов подсказок."""
    return [tip["code"] for tip in FEATURE_TIPS]


def get_tip_by_code(code: str) -> Optional[Dict[str, str]]:
    """Возвращает подсказку по коду."""
    for tip in FEATURE_TIPS:
        if tip["code"] == code:
            return tip
    return None


# ============================================================
# ПРОВЕРКА: надо ли слать?
# ============================================================
def should_send(last_active_at: Optional[datetime]) -> bool:
    """
    True, если юзера не было MIN_DAYS_AWAY..MAX_DAYS_AWAY дней.
    """
    if last_active_at is None:
        return False

    # Приводим к UTC
    if last_active_at.tzinfo is None:
        last_active_at = last_active_at.replace(tzinfo=timezone.utc)

    now = datetime.now(timezone.utc)
    delta = now - last_active_at

    return (
        timedelta(days=MIN_DAYS_AWAY) <= delta
        <= timedelta(days=MAX_DAYS_AWAY)
    )


# ============================================================
# ВЫБОР ПОДСКАЗКИ
# ============================================================
async def pick_unseen_tip(user_id: int) -> Optional[Dict[str, Any]]:
    """
    Возвращает подсказку, которую юзер ещё не видел.
    Если все видел — сбрасывает историю (начинает заново)
    и возвращает случайную.
    """
    # Достаём список виденных кодов
    try:
        async with async_session() as session:
            rows = (await session.execute(
                select(RewardClaim.reward_code)
                .where(RewardClaim.user_id == user_id)
                .where(RewardClaim.reward_code.like(f"{REWARD_PREFIX}%"))
            )).scalars().all()
            seen_codes = {
                rc.replace(REWARD_PREFIX, "", 1) for rc in rows
            }
    except Exception:
        logger.exception("[TIP] failed to load seen codes")
        seen_codes = set()

    all_codes = all_tip_codes()

    # Невиденные
    unseen = [c for c in all_codes if c not in seen_codes]

    if not unseen:
        # Все видел — сбрасываем историю и берём случайную.
        logger.info(f"[TIP] user={user_id} all tips seen, resetting")
        return random.choice(FEATURE_TIPS)

    # Случайная из невиденных
    code = random.choice(unseen)
    for tip in FEATURE_TIPS:
        if tip["code"] == code:
            return tip
    return None


async def mark_tip_seen(user_id: int, code: str) -> bool:
    """
    Помечает подсказку как показанную.
    Возвращает True, если запись создана.
    """
    reward_code = f"{REWARD_PREFIX}{code}"

    try:
        async with async_session() as session:
            claim = RewardClaim(
                user_id=user_id,
                reward_code=reward_code,
                payload={"code": code},
            )
            session.add(claim)
            await session.commit()
        return True
    except Exception:
        # Скорее всего UNIQUE violation — уже видел
        return False


# ============================================================
# ФОРМИРОВАНИЕ СООБЩЕНИЯ
# ============================================================
def format_tip_message(tip: Dict[str, Any]) -> str:
    """
    Собирает текст сообщения для секретной фичи.
    Кратко, с эмодзи, с призывом вернуться.
    """
    emoji = tip.get("emoji", "💡")
    text = tip.get("text", "")
    return (
        f"💡 <b>СЕКРЕТНАЯ ФИЧА ДНЯ</b>\n\n"
        f"{emoji} {text}\n\n"
        f"Возвращайся — тут много всего интересного 👀"
    )


# ============================================================
# ГЛАВНАЯ ФУНКЦИЯ ДЛЯ ПЛАНИРОВЩИКА
# ============================================================
async def prepare_secret_feature(user_id: int) -> Optional[Dict[str, Any]]:
    """
    Готовит payload для hub.schedule_notification.

    Возвращает:
        None — если слать не нужно или нечего.
        dict — {"text": ..., "tip_code": ...} для передачи в hub.

    НЕ помечает подсказку как показанную — это делает планировщик
    после успешной постановки в hub (через mark_tip_seen).
    """
    # 1. Есть ли непоказанные подсказки?
    tip = await pick_unseen_tip(user_id)
    if tip is None:
        return None

    # 2. Собираем текст
    text = format_tip_message(tip)

    return {
        "text": text,
        "tip_code": tip["code"],
    }