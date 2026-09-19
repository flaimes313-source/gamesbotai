from datetime import datetime, timezone
from typing import Optional

try:
    from zoneinfo import ZoneInfo
    HAS_ZONEINFO = True
except ImportError:
    # Python 3.8 не имеет zoneinfo по умолчанию, но у нас 3.11
    HAS_ZONEINFO = False

# Список популярных зон с человеческими названиями
POPULAR_TIMEZONES = [
    ("Europe/Kaliningrad", "🇷🇺 Калининград (UTC+2)"),
    ("Europe/Moscow", "🇷🇺 Москва (UTC+3)"),
    ("Europe/Samara", "🇷🇺 Самара (UTC+4)"),
    ("Asia/Yekaterinburg", "🇷🇺 Екатеринбург (UTC+5)"),
    ("Asia/Omsk", "🇷🇺 Омск (UTC+6)"),
    ("Asia/Krasnoyarsk", "🇷🇺 Красноярск (UTC+7)"),
    ("Asia/Irkutsk", "🇷🇺 Иркутск (UTC+8)"),
    ("Asia/Yakutsk", "🇷🇺 Якутск (UTC+9)"),
    ("Asia/Vladivostok", "🇷🇺 Владивосток (UTC+10)"),
    ("Asia/Magadan", "🇷🇺 Магадан (UTC+11)"),
    ("Asia/Kamchatka", "🇷🇺 Камчатка (UTC+12)"),
    ("Europe/Kiev", "🇺🇦 Киев (UTC+2)"),
    ("Europe/Minsk", "🇧🇾 Минск (UTC+3)"),
    ("Asia/Almaty", "🇰🇿 Алматы (UTC+5)"),
    ("Asia/Tashkent", "🇺🇿 Ташкент (UTC+5)"),
    ("Asia/Tbilisi", "🇬🇪 Тбилиси (UTC+4)"),
    ("Asia/Yerevan", "🇦🇲 Ереван (UTC+4)"),
    ("Asia/Baku", "🇦🇿 Баку (UTC+4)"),
    ("Europe/London", "🇬🇧 Лондон (UTC+0)"),
    ("Europe/Berlin", "🇩🇪 Берлин (UTC+1)"),
    ("Europe/Paris", "🇫🇷 Париж (UTC+1)"),
    ("America/New_York", "🇺🇸 Нью-Йорк (UTC-5)"),
    ("America/Los_Angeles", "🇺🇸 Лос-Анджелес (UTC-8)"),
    ("Asia/Dubai", "🇦🇪 Дубай (UTC+4)"),
    ("Asia/Tokyo", "🇯🇵 Токио (UTC+9)"),
    ("UTC", "🌐 UTC"),
]


def get_local_now(tz_name: str) -> datetime:
    """
    Возвращает текущее время в указанной таймзоне (aware).
    Если tz_name невалидный — возвращает UTC.
    """
    try:
        tz = ZoneInfo(tz_name)
        return datetime.now(tz)
    except Exception:
        return datetime.now(timezone.utc)


def get_local_hour(tz_name: str) -> int:
    """Текущий час в таймзоне юзера (0-23)."""
    return get_local_now(tz_name).hour


def is_night_now(tz_name: str) -> bool:
    """
    Ночь по локальному времени юзера.
    Ночь = 23:00 – 08:00.
    Используется, чтобы не будить юзера напоминаниями.
    """
    hour = get_local_hour(tz_name)
    return hour >= 23 or hour < 8


def format_local_time(tz_name: str, fmt: str = "%H:%M") -> str:
    """Форматирует текущее локальное время."""
    return get_local_now(tz_name).strftime(fmt)


def humanize_datetime(dt: datetime, tz_name: str) -> str:
    """
    Преобразует UTC-datetime в человеческий вид:
    «только что», «5 минут назад», «вчера в 20:30».
    """
    if dt is None:
        return "—"

    # Приводим к aware UTC
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    now = datetime.now(timezone.utc)
    delta = now - dt

    seconds = delta.total_seconds()

    if seconds < 60:
        return "только что"
    if seconds < 3600:
        minutes = int(seconds // 60)
        return f"{minutes} мин назад"
    if seconds < 86400:
        hours = int(seconds // 3600)
        return f"{hours} ч назад"

    # Больше суток — показываем дату в локальной зоне
    try:
        tz = ZoneInfo(tz_name)
        local_dt = dt.astimezone(tz)
    except Exception:
        local_dt = dt

    now_local = now.astimezone(local_dt.tzinfo) if local_dt.tzinfo else now
    if local_dt.date() == now_local.date():
        return f"сегодня в {local_dt.strftime('%H:%M')}"

    from datetime import timedelta
    yesterday = (now_local - timedelta(days=1)).date()
    if local_dt.date() == yesterday:
        return f"вчера в {local_dt.strftime('%H:%M')}"

    return local_dt.strftime("%d.%m в %H:%M")