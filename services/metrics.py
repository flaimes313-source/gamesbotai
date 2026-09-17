from datetime import datetime, timedelta
from sqlalchemy import func, select

from database.connection import async_session
from database.models import (
    Match, Message, Payment, PhotoAnalysis, User, UserTest,
)


async def full_stats() -> dict:
    now = datetime.utcnow()
    day_ago = now - timedelta(days=1)

    async with async_session() as session:
        total_users = (await session.execute(select(func.count(User.id)))).scalar_one()
        dau = (await session.execute(select(func.count(User.id)).where(User.last_active_at >= day_ago))).scalar_one()
        new_users = (await session.execute(select(func.count(User.id)).where(User.created_at >= day_ago))).scalar_one()

        analyses = (await session.execute(select(func.count(PhotoAnalysis.id)))).scalar_one()
        matches = (await session.execute(select(func.count(Match.id)))).scalar_one()
        messages = (await session.execute(select(func.count(Message.id)))).scalar_one()
        tests_done = (await session.execute(select(func.count(UserTest.id)))).scalar_one()

        pro_revenue = (await session.execute(
            select(func.coalesce(func.sum(Payment.amount), 0)).where(Payment.status == "succeeded")
        )).scalar_one()

    return {
        "users": total_users,
        "dau": dau,
        "new": new_users,
        "analyses": analyses,
        "matches": matches,
        "messages": messages,
        "tests": tests_done,
        "pro_revenue": float(pro_revenue or 0),
    }