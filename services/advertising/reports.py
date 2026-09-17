from datetime import datetime, timedelta

from sqlalchemy import func, select

from database.connection import async_session
from database.models import AdvertisingCampaign, UserAdEvent
from utils.logging import get_logger

logger = get_logger(__name__)


async def ads_report(days: int = 30) -> list[dict]:
    """Отчёт по всем кампаниям: показы, клики, CTR, расход."""
    since = datetime.utcnow() - timedelta(days=days)

    async with async_session() as session:
        campaigns = (await session.execute(
            select(AdvertisingCampaign).order_by(AdvertisingCampaign.id.desc())
        )).scalars().all()

        report = []
        for c in campaigns:
            shown = (await session.execute(
                select(func.count(UserAdEvent.id))
                .where(UserAdEvent.campaign_id == c.id)
                .where(UserAdEvent.shown_at >= since)
            )).scalar_one()

            clicked = (await session.execute(
                select(func.count(UserAdEvent.id))
                .where(UserAdEvent.campaign_id == c.id)
                .where(UserAdEvent.clicked_at.isnot(None))
                .where(UserAdEvent.shown_at >= since)
            )).scalar_one()

            ctr = (clicked / shown * 100) if shown else 0.0
            spent = float(c.price_per_impression or 0) * int(shown or 0)

            report.append({
                "id": c.id,
                "name": c.name,
                "status": c.status,
                "shown": int(shown or 0),
                "clicked": int(clicked or 0),
                "ctr": round(ctr, 1),
                "spent": round(spent, 2),
                "budget": float(c.budget or 0),
            })

    return report


def format_ads_report(report: list[dict]) -> str:
    if not report:
        return "📊 Рекламных кампаний пока нет."

    lines = ["📊 <b>Отчёт по рекламе (30 дней)</b>\n"]
    for r in report:
        lines.append(
            f"#{r['id']} <b>{r['name']}</b> [{r['status']}]\n"
            f"  показы: {r['shown']}\n"
            f"  клики: {r['clicked']}\n"
            f"  CTR: <b>{r['ctr']}%</b>\n"
            f"  расход: {r['spent']:.2f} / {r['budget']:.2f} ₽\n"
        )
    return "\n".join(lines)