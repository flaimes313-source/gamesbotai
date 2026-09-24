"""
Единый сервис уведомлений (Этап 1 — инфраструктура).

Зачем:
- Сейчас у каждого типа уведомлений свой loop (daily_sender, chat_reminder,
  premium_reminder, tops_sender, vibe_weekly). Это приводит к дублированию
  логики (тихие часы, лимиты, проверки).
- Hub централизует: настройки юзера, тихие часы, дневной лимит,
  очередь отправки, идемпотентность.

Использование:
    from services.notifications.hub import schedule_notification

    await schedule_notification(
        user_id=user.id,
        kind="horoscope",
        priority=3,
        payload={"horoscope": "..."},
    )

Что НЕ делает hub:
- Не генерирует контент (это делают сервисы фич: karma, horoscope, ...).
- Не выбирает, кому слать (это решают сервисы-источники).
- Не хранит очередь в БД (in-memory — при рестарте бота потеряется,
  но это ок для «мягких» уведомлений).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import func, select

from database.connection import async_session
from database.models import (
    Event,
    User,
    UserNotificationSettings,
)
from services.feature_flags import is_enabled
from services.timezones import get_local_hour, is_night_now
from utils.logging import get_logger

logger = get_logger(__name__)


# ============================================================
# КОНСТАНТЫ
# ============================================================

# Максимум проактивных уведомлений в день (не считая ответов на действия).
MAX_DAILY_PROACTIVE = 2

# Тихие часы — используем существующий хелпер is_night_now.
# Не шлём между 23:00 и 08:00 по TZ юзера.

# Приоритеты: 1 — критично, 5 — можно пропустить.
# Если дневной лимит уже набран, отбрасываются уведомления
# с приоритетом >= 4.
PRIORITY_DROP_THRESHOLD = 4

# Интервал воркера
WORKER_INTERVAL_SECONDS = 15 * 60  # 15 минут

# Маппинг kind → ключ feature flag.
# Если флаг выключен — уведомление не отправится.
KIND_TO_FLAG: Dict[str, str] = {
    "daily_result": "daily_content_enabled",
    "horoscope": "horoscope_enabled",
    "secret_feature": "secret_feature_enabled",
    "profile_views": "profile_views_enabled",
    "weekly_vibe": "weekly_vibe_enabled",
    "tops": "tops_enabled",
    "premium_reminder": "premium_reminder_enabled",
}

# Маппинг kind → поле в UserNotificationSettings.
# Если поле False — юзер отключил эту категорию.
KIND_TO_SETTING: Dict[str, str] = {
    "daily_result": "daily_result_enabled",
    "horoscope": "horoscope_enabled",
    "secret_feature": "secret_feature_enabled",
    "profile_views": "profile_views_enabled",
    "weekly_vibe": "weekly_vibe_enabled",
    "tops": "tops_enabled",
    "premium_reminder": "premium_reminder_enabled",
}

# Маппинг kind → event name (для идемпотентности и аналитики).
KIND_TO_EVENT: Dict[str, str] = {
    "daily_result": "daily_sent",
    "horoscope": "horoscope_sent",
    "secret_feature": "secret_feature_sent",
    "profile_views": "profile_views_sent",
    "weekly_vibe": "vibe_weekly_sent",
    "tops": "tops_sent",
    "premium_reminder": "premium_reminder_sent",
}


# ============================================================
# ОЧЕРЕДЬ (in-memory)
# ============================================================
# Структура: {user_id: [ {kind, priority, payload, enqueued_at}, ... ]}
_queue: Dict[int, List[Dict[str, Any]]] = {}
_queue_lock = asyncio.Lock()


# ============================================================
# НАСТРОЙКИ ЮЗЕРА
# ============================================================
async def get_notification_settings(user_id: int) -> Dict[str, bool]:
    """
    Возвращает настройки уведомлений юзера.
    Если строки нет — создаёт с дефолтами и возвращает.
    """
    async with async_session() as session:
        s = (await session.execute(
            select(UserNotificationSettings)
            .where(UserNotificationSettings.user_id == user_id)
        )).scalar_one_or_none()

        if s is None:
            s = UserNotificationSettings(user_id=user_id)
            session.add(s)
            await session.commit()
            await session.refresh(s)

        return {
            "daily_result_enabled": s.daily_result_enabled,
            "horoscope_enabled": s.horoscope_enabled,
            "secret_feature_enabled": s.secret_feature_enabled,
            "profile_views_enabled": s.profile_views_enabled,
            "weekly_vibe_enabled": s.weekly_vibe_enabled,
            "tops_enabled": s.tops_enabled,
            "premium_reminder_enabled": s.premium_reminder_enabled,
        }


async def update_notification_setting(
    user_id: int,
    key: str,
    value: bool,
) -> bool:
    """
    Меняет один тумблер. Возвращает True, если получилось.
    key — имя поля в UserNotificationSettings (например, "horoscope_enabled").
    """
    allowed = set(KIND_TO_SETTING.values())
    if key not in allowed:
        logger.warning(f"[HUB] unknown setting key: {key}")
        return False

    async with async_session() as session:
        s = (await session.execute(
            select(UserNotificationSettings)
            .where(UserNotificationSettings.user_id == user_id)
        )).scalar_one_or_none()

        if s is None:
            s = UserNotificationSettings(user_id=user_id)
            session.add(s)

        setattr(s, key, value)
        await session.commit()

    logger.info(f"[HUB] user={user_id} {key}={value}")
    return True


# ============================================================
# ПРОВЕРКИ ПЕРЕД ОТПРАВКОЙ
# ============================================================
async def _already_sent_today(user_id: int, kind: str) -> bool:
    """
    Проверяет через events, не отправляли ли сегодня это уведомление.
    Защита от дублей при рестарте или повторных вызовах.
    """
    event_name = KIND_TO_EVENT.get(kind)
    if not event_name:
        return False

    today_start = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    try:
        async with async_session() as session:
            cnt = (await session.execute(
                select(func.count(Event.id))
                .where(Event.name == event_name)
                .where(Event.user_id == user_id)
                .where(Event.created_at >= today_start)
            )).scalar_one()
            return cnt > 0
    except Exception:
        logger.exception("[HUB] already_sent_today failed")
        return False


async def _count_sent_today(user_id: int) -> int:
    """
    Считает, сколько проактивных уведомлений ушло сегодня.
    Считает только те, что в KIND_TO_EVENT (т.е. через hub).
    """
    event_names = list(KIND_TO_EVENT.values())
    today_start = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    try:
        async with async_session() as session:
            cnt = (await session.execute(
                select(func.count(Event.id))
                .where(Event.name.in_(event_names))
                .where(Event.user_id == user_id)
                .where(Event.created_at >= today_start)
            )).scalar_one()
            return int(cnt)
    except Exception:
        logger.exception("[HUB] count_sent_today failed")
        return 0


async def can_send_now(
    user_id: int,
    kind: str,
    priority: int = 3,
    tz_name: Optional[str] = None,
) -> tuple[bool, str]:
    """
    Проверяет, можно ли отправить уведомление сейчас.

    Возвращает (allowed, reason):
        allowed=True  — можно слать.
        allowed=False — reason объясняет, почему нет.

    Проверки:
    1. Feature flag (глобально выключено?).
    2. Настройки юзера (категория отключена?).
    3. Тихие часы (23:00–08:00 по TZ).
    4. Дневной лимит (MAX_DAILY_PROACTIVE).
    5. Дубли (уже слали сегодня?).
    """
    # 1. Feature flag
    flag_key = KIND_TO_FLAG.get(kind)
    if flag_key:
        enabled = await is_enabled(flag_key, default=True)
        if not enabled:
            return False, "flag_disabled"

    # 2. Настройки юзера
    settings_key = KIND_TO_SETTING.get(kind)
    if settings_key:
        settings = await get_notification_settings(user_id)
        if not settings.get(settings_key, True):
            return False, "user_disabled"

    # 3. Тихие часы
    if tz_name:
        if is_night_now(tz_name):
            return False, "night_hours"

    # 4. Дневной лимит
    sent_today = await _count_sent_today(user_id)
    if sent_today >= MAX_DAILY_PROACTIVE:
        # Если приоритет низкий — отбрасываем
        if priority >= PRIORITY_DROP_THRESHOLD:
            return False, "daily_limit_low_priority"
        # Если высокий — всё равно шлём, но помечаем
        return True, "daily_limit_but_high_priority"

    # 5. Дубли
    if await _already_sent_today(user_id, kind):
        return False, "already_sent_today"

    return True, "ok"


# ============================================================
# ПОСТАНОВКА В ОЧЕРЕДЬ
# ============================================================
async def schedule_notification(
    user_id: int,
    kind: str,
    priority: int = 3,
    payload: Optional[Dict[str, Any]] = None,
    tz_name: Optional[str] = None,
) -> bool:
    """
    Ставит уведомление в очередь.

    Параметры:
        user_id — кому.
        kind — тип (horoscope, secret_feature, profile_views, ...).
        priority — 1 (высокий) .. 5 (низкий).
        payload — данные для отправки (текст, кнопки, и т.п.).
        tz_name — TZ юзера (если есть; иначе возьмём из БД в воркере).

    Возвращает True, если принято в очередь.
    """
    if not user_id:
        return False

    # Проверка can_send_now — быстрый фильтр.
    # Если tz_name не передан — воркер сам проверит.
    if tz_name:
        allowed, reason = await can_send_now(
            user_id, kind, priority, tz_name
        )
        if not allowed:
            logger.info(
                f"[HUB] skip user={user_id} kind={kind} reason={reason}"
            )
            return False

    async with _queue_lock:
        _queue.setdefault(user_id, []).append({
            "kind": kind,
            "priority": priority,
            "payload": payload or {},
            "enqueued_at": datetime.now(timezone.utc),
            "tz_name": tz_name,
        })

    logger.info(f"[HUB] queued user={user_id} kind={kind} prio={priority}")
    return True


# ============================================================
# ОТПРАВКА ОДНОГО УВЕДОМЛЕНИЯ
# ============================================================
async def _send_notification(
    bot: Bot,
    user: User,
    item: Dict[str, Any],
) -> bool:
    """
    Отправляет одно уведомление из очереди.
    Возвращает True, если успешно.
    """
    kind = item["kind"]
    payload = item.get("payload", {})
    event_name = KIND_TO_EVENT.get(kind)

    text = payload.get("text") or ""
    photo_bytes = payload.get("photo_bytes")
    reply_markup = payload.get("reply_markup")

    if not text and not photo_bytes:
        logger.warning(f"[HUB] empty payload for kind={kind} user={user.id}")
        return False

    # Финальная проверка (TZ может быть известна только сейчас)
    allowed, reason = await can_send_now(
        user.id, kind, item.get("priority", 3), user.timezone
    )
    if not allowed and reason != "daily_limit_but_high_priority":
        logger.info(
            f"[HUB] abort send user={user.id} kind={kind} reason={reason}"
        )
        return False

    try:
        from aiogram.types import BufferedInputFile

        if photo_bytes:
            await bot.send_photo(
                user.telegram_id,
                BufferedInputFile(photo_bytes, filename="vibe.png"),
                caption=text or None,
                reply_markup=reply_markup,
            )
        else:
            await bot.send_message(
                user.telegram_id,
                text,
                reply_markup=reply_markup,
            )
    except Exception as e:
        # TelegramForbiddenError — юзер заблокировал
        from aiogram.exceptions import TelegramForbiddenError
        if isinstance(e, TelegramForbiddenError):
            async with async_session() as session:
                u = (await session.execute(
                    select(User).where(User.id == user.id)
                )).scalar_one_or_none()
                if u:
                    u.is_blocked = True
                    await session.commit()
            logger.info(f"[HUB] user={user.id} blocked the bot")
        else:
            logger.exception(f"[HUB] send failed user={user.id} kind={kind}")
        return False

    # Track события
    try:
        from services.analytics.tracker import track
        if event_name:
            await track(
                event_name,
                telegram_id=user.telegram_id,
                payload={"kind": kind},
            )
    except Exception:
        logger.exception("[HUB] track failed")

    return True


# ============================================================
# ВОРКЕР
# ============================================================
async def _process_queue(bot: Bot) -> int:
    """
    Проходит по очереди, отправляет готовые, чистит старые.
    Возвращает количество отправленных.
    """
    sent = 0
    now = datetime.now(timezone.utc)

    # Снимок ключей
    async with _queue_lock:
        user_ids = list(_queue.keys())

    for user_id in user_ids:
        # Достаём юзера
        async with async_session() as session:
            user = (await session.execute(
                select(User).where(User.id == user_id)
            )).scalar_one_or_none()

        if user is None or user.is_blocked:
            async with _queue_lock:
                _queue.pop(user_id, None)
            continue

        # Обрабатываем элементы
        async with _queue_lock:
            items = _queue.get(user_id, [])
            # Сортируем по приоритету (1 — выше)
            items = sorted(items, key=lambda x: x.get("priority", 3))

        for item in items:
            # Слишком старые (больше 24 часов) — выбрасываем
            enq = item.get("enqueued_at")
            if enq and (now - enq) > timedelta(hours=24):
                continue

            ok = await _send_notification(bot, user, item)
            if ok:
                sent += 1
                # После успешной отправки — пауза
                await asyncio.sleep(0.05)
            # Убираем из очереди в любом случае
            async with _queue_lock:
                try:
                    _queue[user_id].remove(item)
                except (ValueError, KeyError):
                    pass

        # Если очередь юзера пуста — удаляем ключ
        async with _queue_lock:
            if user_id in _queue and not _queue[user_id]:
                _queue.pop(user_id, None)

    return sent


async def notification_worker_loop(bot: Bot) -> None:
    """
    Бесконечный цикл: раз в WORKER_INTERVAL_SECONDS обрабатывает очередь.
    """
    while True:
        try:
            sent = await _process_queue(bot)
            if sent:
                logger.info(f"[HUB] worker sent={sent} queue_size={sum(len(v) for v in _queue.values())}")
        except Exception:
            logger.exception("[HUB] worker iteration failed")

        await asyncio.sleep(WORKER_INTERVAL_SECONDS)


# ============================================================
# УТИЛИТЫ ДЛЯ UI
# ============================================================
def notifications_menu_kb(settings: Dict[str, bool]) -> InlineKeyboardMarkup:
    """
    Клавиатура настроек уведомлений.
    settings — результат get_notification_settings(user_id).
    """
    def toggle(name: str, label: str, key: str) -> InlineKeyboardButton:
        mark = "✅" if settings.get(key, True) else "❌"
        return InlineKeyboardButton(
            text=f"{mark} {label}",
            callback_data=f"notif_toggle_{name}",
        )

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [toggle("daily_result", "😂 Прикол дня", "daily_result_enabled")],
            [toggle("horoscope", "🔮 Гороскоп", "horoscope_enabled")],
            [toggle("secret_feature", "💡 Секретные фичи", "secret_feature_enabled")],
            [toggle("profile_views", "👀 Просмотры профиля", "profile_views_enabled")],
            [toggle("weekly_vibe", "🗓 Вайб-отчёт", "weekly_vibe_enabled")],
            [toggle("tops", "🏆 Топы", "tops_enabled")],
            [toggle("premium_reminder", "💎 PRO-напоминания", "premium_reminder_enabled")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="settings")],
        ]
    )


def available_kinds() -> List[str]:
    """Список всех поддерживаемых типов уведомлений."""
    return list(KIND_TO_EVENT.keys())