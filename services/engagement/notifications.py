"""
Очередь уведомлений о достижениях, уровнях, стриках, наградах.
"""
from typing import Optional

from aiogram import Bot

from utils.logging import get_logger

logger = get_logger(__name__)


_queue: dict[int, list] = {}


def add_achievement_notification(telegram_id: int, title: str, description: str, emoji: str) -> None:
    if telegram_id not in _queue:
        _queue[telegram_id] = []
    _queue[telegram_id].append({
        "type": "achievement",
        "text": (
            f"🏆 <b>НОВОЕ ДОСТИЖЕНИЕ</b>\n\n"
            f"{emoji} <b>{title}</b>\n\n"
            f"<i>{description}</i>"
        ),
    })


def add_level_up_notification(
    telegram_id: int,
    level: int,
    title: str,
    total_points: int,
    to_next: int,
) -> None:
    if telegram_id not in _queue:
        _queue[telegram_id] = []

    if to_next > 0:
        progress_line = f"📈 До уровня {level + 1}: <b>{to_next}</b> очков"
    else:
        progress_line = "🏆 <b>Максимальный уровень!</b>"

    _queue[telegram_id].append({
        "type": "level_up",
        "text": (
            f"🎉 <b>НОВЫЙ УРОВЕНЬ!</b>\n\n"
            f"🏅 Уровень <b>{level}</b> — {title}\n"
            f"⭐ Очки: <b>{total_points}</b>\n"
            f"{progress_line}"
        ),
    })


def add_streak_notification(telegram_id: int, streak: int) -> None:
    if telegram_id not in _queue:
        _queue[telegram_id] = []

    streak_lines = {
        3: "🔥 Ты заходил 3 дня подряд!",
        7: "🔥 Целая неделя с Вайбми!",
        14: "🔥 2 недели подряд!",
        30: "🔥 Месяц с Вайбми!",
        100: "🔥 100 дней подряд!",
    }

    text = streak_lines.get(streak, f"🔥 Стрик: {streak} дней!")
    _queue[telegram_id].append({
        "type": "streak",
        "text": f"🔥 <b>СТРИК {streak} ДНЕЙ!</b>\n\n{text}",
    })


def add_custom_notification(telegram_id: int, text: str) -> None:
    """Добавляет произвольное уведомление."""
    if telegram_id not in _queue:
        _queue[telegram_id] = []
    _queue[telegram_id].append({
        "type": "custom",
        "text": text,
    })


async def flush_notifications(bot: Bot, telegram_id: int) -> None:
    if telegram_id not in _queue:
        return

    notifications = _queue.pop(telegram_id, [])
    if not notifications:
        return

    for notif in notifications:
        try:
            await bot.send_message(telegram_id, notif["text"])
        except Exception:
            logger.exception(f"[NOTIF] Failed to send {notif['type']} to {telegram_id}")


def has_pending(telegram_id: int) -> bool:
    return telegram_id in _queue and len(_queue[telegram_id]) > 0