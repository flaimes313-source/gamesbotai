from datetime import datetime, timedelta

from sqlalchemy import func, select

from database.connection import async_session
from database.models import Event, ExperimentAssignment, PhotoAnalysis, User
from utils.logging import get_logger

logger = get_logger(__name__)


async def ab_photo_prompt_report(days: int = 30) -> list[dict]:
    """
    Возвращает по каждому варианту:
    - количество анализов
    - количество share_generated
    - share rate (%)
    """
    since = datetime.utcnow() - timedelta(days=days)

    async with async_session() as session:
        # Все назначения
        assignments = (await session.execute(
            select(ExperimentAssignment).where(ExperimentAssignment.experiment == "photo_prompt")
        )).scalars().all()

        # Разбиваем telegram_id по вариантам
        by_variant: dict[str, set[int]] = {}
        for a in assignments:
            by_variant.setdefault(a.variant, set()).add(a.telegram_id)

        report = []
        for variant, tids in by_variant.items():
            # Анализы за период
            analyses_cnt = (await session.execute(
                select(func.count(PhotoAnalysis.id))
                .join(User, User.id == PhotoAnalysis.user_id)
                .where(User.telegram_id.in_(tids))
                .where(PhotoAnalysis.created_at >= since)
                .where(PhotoAnalysis.prompt_version == variant)
            )).scalar_one()

            # Шары за период
            shares_cnt = (await session.execute(
                select(func.count(Event.id))
                .where(Event.name == "share_generated")
                .where(Event.telegram_id.in_(tids))
                .where(Event.created_at >= since)
            )).scalar_one()

            share_rate = (shares_cnt / analyses_cnt * 100) if analyses_cnt else 0.0

            report.append({
                "variant": variant,
                "users": len(tids),
                "analyses": int(analyses_cnt),
                "shares": int(shares_cnt),
                "share_rate": round(share_rate, 1),
            })

    return sorted(report, key=lambda r: r["variant"])


def format_ab_report(report: list[dict]) -> str:
    if not report:
        return "Пока нет данных по A/B."

    lines = ["🧪 <b>A/B ТЕСТ ПРОМТОВ (30 дней)</b>\n"]
    for r in report:
        lines.append(
            f"<b>{r['variant']}</b>\n"
            f"  пользователей: {r['users']}\n"
            f"  анализов: {r['analyses']}\n"
            f"  поделились: {r['shares']}\n"
            f"  share rate: <b>{r['share_rate']}%</b>\n"
        )
    return "\n".join(lines)