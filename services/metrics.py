from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from database.connection import async_session
from database.models import (
    Chat,
    Event,
    Match,
    Message,
    Payment,
    PhotoAnalysis,
    User,
    UserTest,
)


# ============================================================
# Общая статистика
# ============================================================
async def full_stats() -> dict:
    now = datetime.now(timezone.utc)
    day_ago = now - timedelta(days=1)

    async with async_session() as session:
        total_users = (await session.execute(select(func.count(User.id)))).scalar_one()
        dau = (await session.execute(
            select(func.count(User.id)).where(User.last_active_at >= day_ago)
        )).scalar_one()
        new_users = (await session.execute(
            select(func.count(User.id)).where(User.created_at >= day_ago)
        )).scalar_one()

        analyses = (await session.execute(select(func.count(PhotoAnalysis.id)))).scalar_one()
        matches = (await session.execute(select(func.count(Match.id)))).scalar_one()
        messages = (await session.execute(select(func.count(Message.id)))).scalar_one()
        tests_done = (await session.execute(select(func.count(UserTest.id)))).scalar_one()
        chats_total = (await session.execute(select(func.count(Chat.id)))).scalar_one()

        pro_revenue = (await session.execute(
            select(func.coalesce(func.sum(Payment.amount), 0)).where(Payment.status == "succeeded")
        )).scalar_one()

    return {
        "users": int(total_users or 0),
        "dau": int(dau or 0),
        "new": int(new_users or 0),
        "analyses": int(analyses or 0),
        "matches": int(matches or 0),
        "messages": int(messages or 0),
        "tests": int(tests_done or 0),
        "chats_total": int(chats_total or 0),
        "pro_revenue": float(pro_revenue or 0),
    }


# ============================================================
# Воронка
# ============================================================
async def funnel_stats(days: int = 30) -> dict:
    since = datetime.now(timezone.utc) - timedelta(days=days)

    steps = [
        ("start", "started"),
        ("photo_sent", "photo_sent"),
        ("analysis_completed", "analyses"),
        ("share_generated", "shares"),
        ("referral_opened", "referrals_opened"),
        ("new_users", "new_users"),
        ("game_opt_in", "game_opt_in"),
        ("match_created", "matches"),
        ("chat_message_sent", "messages"),
    ]

    async with async_session() as session:
        result = {}
        for event_name, key in steps:
            cnt = (await session.execute(
                select(func.count(func.distinct(Event.telegram_id)))
                .where(Event.name == event_name)
                .where(Event.created_at >= since)
                .where(Event.telegram_id.isnot(None))
            )).scalar_one()
            result[key] = int(cnt or 0)

    return result


# ============================================================
# Статистика по чатам
# ============================================================
async def chats_stats(days: int = 7) -> dict:
    since = datetime.now(timezone.utc) - timedelta(days=days)

    async with async_session() as session:
        total_chats = (await session.execute(select(func.count(Chat.id)))).scalar_one()

        active_chat_ids = (await session.execute(
            select(Message.chat_id)
            .where(Message.created_at >= since)
            .where(Message.chat_id.isnot(None))
            .group_by(Message.chat_id)
        )).scalars().all()

        active_count = len(active_chat_ids)

        total_messages = (await session.execute(
            select(func.count(Message.id))
            .where(Message.created_at >= since)
            .where(Message.chat_id.isnot(None))
        )).scalar_one()

        avg_messages = (total_messages / active_count) if active_count else 0.0

        top_rows = (await session.execute(
            select(Message.chat_id, func.count(Message.id).label("cnt"))
            .where(Message.created_at >= since)
            .where(Message.chat_id.isnot(None))
            .group_by(Message.chat_id)
            .order_by(func.count(Message.id).desc())
            .limit(5)
        )).all()

        top = []
        for chat_id, cnt in top_rows:
            chat = (await session.execute(
                select(Chat).where(Chat.id == chat_id)
            )).scalar_one_or_none()
            if chat is None:
                continue
            u1 = (await session.execute(
                select(User).where(User.id == chat.user1_id)
            )).scalar_one_or_none()
            u2 = (await session.execute(
                select(User).where(User.id == chat.user2_id)
            )).scalar_one_or_none()
            top.append({
                "chat_id": chat_id,
                "count": int(cnt),
                "user1": (u1.first_name if u1 else None) or "—",
                "user2": (u2.first_name if u2 else None) or "—",
            })

    return {
        "days": days,
        "total_chats": int(total_chats or 0),
        "active_chats": active_count,
        "total_messages": int(total_messages or 0),
        "avg_messages": round(avg_messages, 1),
        "top": top,
    }


# ============================================================
# Статистика по таймзонам (топ-5)
# ============================================================
async def timezones_stats() -> list[dict]:
    async with async_session() as session:
        rows = (await session.execute(
            select(User.timezone, func.count(User.id).label("cnt"))
            .group_by(User.timezone)
            .order_by(func.count(User.id).desc())
            .limit(5)
        )).all()

    return [{"timezone": tz, "count": int(cnt)} for tz, cnt in rows]