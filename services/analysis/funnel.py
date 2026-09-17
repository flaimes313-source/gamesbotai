from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import distinct, func, select

from database.connection import async_session
from database.models import Event
from utils.logging import get_logger

logger = get_logger(__name__)


# Порядок шагов воронки (см. ТЗ п.45)
FUNNEL_STEPS = [
    ("start", "Начали работу"),
    ("photo_sent", "Отправили фото"),
    ("analysis_completed", "Получили результат"),
    ("share_generated", "Поделились"),
    ("referral_opened", "Переходы по ссылке"),
    ("new_users", "Новые пользователи"),
    ("game_opt_in", "Вошли в игру"),
    ("match_created", "Получили match"),
    ("message_sent", "Отправили сообщение"),
]


async def get_funnel(days: int = 30) -> list[dict]:
    """
    Возвращает воронку за последние N дней:
    [
        {"step": "start", "label": "Начали работу", "count": 1000, "conversion": 100.0},
        {"step": "photo_sent", ...}
        ...
    ]
    """
    since = datetime.utcnow() - timedelta(days=days)

    async with async_session() as session:
        counts: dict[str, int] = {}
        for step, _label in FUNNEL_STEPS:
            cnt = (await session.execute(
                select(func.count(distinct(Event.user_id)))
                .where(Event.name == step)
                .where(Event.created_at >= since)
                .where(Event.user_id.isnot(None))
            )).scalar_one()
            counts[step] = int(cnt or 0)

    # Первый шаг — база для конверсии
    base = counts.get("start", 0) or 1

    result: list[dict] = []
    for step, label in FUNNEL_STEPS:
        cnt = counts.get(step, 0)
        result.append({
            "step": step,
            "label": label,
            "count": cnt,
            "conversion": round(cnt / base * 100, 1),
        })
    return result


def format_funnel(funnel: list[dict]) -> str:
    """Форматирует воронку в текст для Telegram."""
    if not funnel:
        return "Воронка пуста."

    lines = ["📉 <b>ВОРОНКА (30 дней)</b>\n"]
    prev_count: Optional[int] = None

    for row in funnel:
        arrow = ""
        if prev_count is not None and prev_count > 0:
            step_conv = row["count"] / prev_count * 100
            arrow = f"  ↓ {step_conv:.0f}%"
        lines.append(
            f"<b>{row['label']}</b>: {row['count']} ({row['conversion']}%){arrow}"
        )
        prev_count = row["count"]

    return "\n".join(lines)