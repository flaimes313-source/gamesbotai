"""
Отчёты по кампаниям подписок (Этап 5).

Используется в админке:
- 📊 Карточка кампании (счётчики + стоимость).
- 📋 Список подписчиков.
- 📊 Разбивка по дням.
- 📤 Экспорт в CSV.

Всё считается на лету из SubscriptionEvent + User.
Никаких миграций, никаких новых таблиц.
"""

from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select

from database.connection import async_session
from database.models import SubscriptionCampaign, SubscriptionEvent, User
from utils.logging import get_logger

logger = get_logger(__name__)


# ============================================================
# СТАТИСТИКА КАМПАНИИ
# ============================================================
async def get_campaign_stats(campaign_id: int) -> Optional[Dict[str, Any]]:
    """
    Собирает полную статистику кампании.

    Возвращает:
        {
            "campaign": {
                "id", "name", "status", "is_active",
                "channel_id", "channel_username", "channel_link",
                "price_per_subscription", "subscriber_limit", "budget",
                "started_at", "ended_at",
            },
            "counts": {
                "total": int,       # все, кто попал в SubscriptionEvent
                "confirmed": int,   # подписался
                "pending": int,     # ожидает
            },
            "money": {
                "total_cost": float,     # confirmed * price
                "budget": float,         # из кампании
                "budget_left": float,    # budget - total_cost
                "budget_used_pct": float,
            },
            "limits": {
                "subscriber_limit": int,
                "subscriber_left": int,
                "subscriber_used_pct": float,
            },
            "period": {
                "started_at": datetime | None,
                "ended_at": datetime | None,
                "is_active": bool,
            },
        }

    None — если кампания не найдена.
    """
    async with async_session() as session:
        campaign = (await session.execute(
            select(SubscriptionCampaign).where(SubscriptionCampaign.id == campaign_id)
        )).scalar_one_or_none()

        if campaign is None:
            return None

        # Все события по кампании
        total = (await session.execute(
            select(func.count(SubscriptionEvent.id))
            .where(SubscriptionEvent.campaign_id == campaign_id)
        )).scalar_one()

        confirmed = (await session.execute(
            select(func.count(SubscriptionEvent.id))
            .where(SubscriptionEvent.campaign_id == campaign_id)
            .where(SubscriptionEvent.status == "confirmed")
        )).scalar_one()

        pending = total - confirmed

        # Снимок данных кампании (до выхода из сессии)
        camp = {
            "id": campaign.id,
            "name": campaign.name,
            "status": campaign.status,
            "is_active": campaign.is_active,
            "channel_id": campaign.channel_id,
            "channel_username": campaign.channel_username,
            "channel_link": campaign.channel_link,
            "price_per_subscription": float(campaign.price_per_subscription or 0),
            "subscriber_limit": int(campaign.subscriber_limit or 0),
            "budget": float(campaign.budget or 0),
            "started_at": campaign.started_at,
            "ended_at": campaign.ended_at,
        }

    # Считаем деньги
    price = camp["price_per_subscription"]
    total_cost = price * confirmed
    budget = camp["budget"]
    budget_left = max(0.0, budget - total_cost)
    budget_used_pct = (total_cost / budget * 100) if budget > 0 else 0.0

    # Считаем лимиты
    sub_limit = camp["subscriber_limit"]
    sub_left = max(0, sub_limit - confirmed) if sub_limit > 0 else 0
    sub_used_pct = (confirmed / sub_limit * 100) if sub_limit > 0 else 0.0

    return {
        "campaign": camp,
        "counts": {
            "total": int(total),
            "confirmed": int(confirmed),
            "pending": int(pending),
        },
        "money": {
            "total_cost": total_cost,
            "budget": budget,
            "budget_left": budget_left,
            "budget_used_pct": round(budget_used_pct, 1),
        },
        "limits": {
            "subscriber_limit": sub_limit,
            "subscriber_left": sub_left,
            "subscriber_used_pct": round(sub_used_pct, 1),
        },
        "period": {
            "started_at": camp["started_at"],
            "ended_at": camp["ended_at"],
            "is_active": camp["is_active"],
        },
    }


# ============================================================
# СПИСОК ПОДПИСЧИКОВ
# ============================================================
async def get_campaign_subscribers(
    campaign_id: int,
    limit: int = 50,
    offset: int = 0,
    only_confirmed: bool = True,
) -> List[Dict[str, Any]]:
    """
    Возвращает список подписчиков кампании.
    Сортировка — по дате (свежие вверху).

    only_confirmed=True — только status="confirmed".
    only_confirmed=False — все (pending + confirmed).
    """
    async with async_session() as session:
        q = (
            select(SubscriptionEvent, User)
            .join(User, User.id == SubscriptionEvent.user_id)
            .where(SubscriptionEvent.campaign_id == campaign_id)
        )
        if only_confirmed:
            q = q.where(SubscriptionEvent.status == "confirmed")
        q = q.order_by(SubscriptionEvent.confirmed_at.desc().nullslast(),
                       SubscriptionEvent.id.desc())
        q = q.limit(limit).offset(offset)

        rows = (await session.execute(q)).all()

    result = []
    for ev, u in rows:
        result.append({
            "user_id": u.id,
            "telegram_id": u.telegram_id,
            "username": u.username,
            "first_name": u.first_name,
            "status": ev.status,
            "checked_at": ev.checked_at,
            "confirmed_at": ev.confirmed_at,
        })
    return result


# ============================================================
# РАЗБИВКА ПО ДНЯМ
# ============================================================
async def get_campaign_daily_breakdown(campaign_id: int) -> List[Dict[str, Any]]:
    """
    Возвращает разбивку подтверждённых подписчиков по дням.

    [{"date": date, "count": int, "cost": float}, ...]
    """
    async with async_session() as session:
        rows = (await session.execute(
            select(
                func.date(SubscriptionEvent.confirmed_at).label("d"),
                func.count(SubscriptionEvent.id).label("cnt"),
            )
            .where(SubscriptionEvent.campaign_id == campaign_id)
            .where(SubscriptionEvent.status == "confirmed")
            .where(SubscriptionEvent.confirmed_at.isnot(None))
            .group_by(func.date(SubscriptionEvent.confirmed_at))
            .order_by(func.date(SubscriptionEvent.confirmed_at))
        )).all()

        campaign = (await session.execute(
            select(SubscriptionCampaign.price_per_subscription)
            .where(SubscriptionCampaign.id == campaign_id)
        )).scalar_one_or_none()

    price = float(campaign or 0)

    result = []
    for d, cnt in rows:
        result.append({
            "date": d,
            "count": int(cnt),
            "cost": round(int(cnt) * price, 2),
        })
    return result


# ============================================================
# ФОРМАТИРОВАНИЕ ДЛЯ UI
# ============================================================
def _fmt_dt(dt: Optional[datetime]) -> str:
    if dt is None:
        return "—"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.strftime("%d.%m.%Y")


def _fmt_dt_full(dt: Optional[datetime]) -> str:
    if dt is None:
        return "—"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.strftime("%d.%m %H:%M")


def format_campaign_card(stats: Dict[str, Any]) -> str:
    """Карточка кампании для админки."""
    c = stats["campaign"]
    counts = stats["counts"]
    money = stats["money"]
    limits = stats["limits"]

    # Статус
    if c["is_active"]:
        status_line = "🟢 <b>Активна</b>"
    else:
        status_line = "🔴 <b>Остановлена</b>"

    # Период
    period_line = f"📅 {_fmt_dt(c['started_at'])}"
    if c["ended_at"]:
        period_line += f" — {_fmt_dt(c['ended_at'])}"
    else:
        period_line += " — сейчас"

    # Стоимость
    if money["budget"] > 0:
        money_line = (
            f"💰 Стоимость: <b>{money['total_cost']:.0f} ₽</b>\n"
            f"   Бюджет: {money['budget']:.0f} ₽ "
            f"(исп. {money['budget_used_pct']}%)"
        )
    else:
        money_line = f"💰 Стоимость: <b>{money['total_cost']:.0f} ₽</b>"

    # Лимит
    if limits["subscriber_limit"] > 0:
        limit_line = (
            f"👥 Лимит подписчиков: {counts['confirmed']}/"
            f"{limits['subscriber_limit']} "
            f"({limits['subscriber_used_pct']}%)"
        )
    else:
        limit_line = "👥 Лимит подписчиков: без лимита"

    return (
        f"📣 <b>КАМПАНИЯ #{c['id']} — {c['name']}</b>\n\n"
        f"{status_line}\n"
        f"📢 Канал: {c['channel_username'] or '—'}\n"
        f"{period_line}\n\n"
        f"📊 <b>СТАТИСТИКА</b>\n"
        f"• Всего пришло: <b>{counts['total']}</b>\n"
        f"• Подтверждено: <b>{counts['confirmed']}</b>\n"
        f"• Ожидает: <b>{counts['pending']}</b>\n\n"
        f"{money_line}\n"
        f"{limit_line}"
    )


def format_subscribers_list(
    subscribers: List[Dict[str, Any]],
    total: int,
    page: int = 1,
    per_page: int = 50,
    only_confirmed: bool = True,
) -> str:
    """Список подписчиков."""
    title = "📋 <b>ПОДПИСЧИКИ</b>" if only_confirmed else "📋 <b>ВСЕ СОБЫТИЯ</b>"
    lines = [f"{title} (всего {total})", ""]

    if not subscribers:
        lines.append("<i>Пусто.</i>")
        return "\n".join(lines)

    start_n = (page - 1) * per_page + 1
    for i, s in enumerate(subscribers, start=start_n):
        uname = f"@{s['username']}" if s["username"] else f"id{s['telegram_id']}"
        name = s["first_name"] or "—"
        dt = _fmt_dt_full(s.get("confirmed_at") or s.get("checked_at"))
        mark = "✅" if s["status"] == "confirmed" else "⏳"
        lines.append(f"{i}. {mark} {uname} — {name} ({dt})")

    return "\n".join(lines)


def format_daily_breakdown(
    breakdown: List[Dict[str, Any]],
    campaign_name: str,
    price: float,
) -> str:
    """Разбивка по дням."""
    lines = [f"📊 <b>РАЗБИВКА ПО ДНЯМ</b>", f"Кампания: {campaign_name}", ""]

    if not breakdown:
        lines.append("<i>Пока нет подтверждённых подписок.</i>")
        return "\n".join(lines)

    total_count = 0
    total_cost = 0.0

    for row in breakdown:
        d = row["date"]
        dt_str = d.strftime("%d.%m") if hasattr(d, "strftime") else str(d)
        lines.append(f"📅 <b>{dt_str}</b> — {row['count']} ({row['cost']:.0f} ₽)")
        total_count += row["count"]
        total_cost += row["cost"]

    lines.append("")
    lines.append(f"━━━━━━━━━━━━━━━━━━")
    lines.append(f"<b>Итого: {total_count} подписчиков, {total_cost:.0f} ₽</b>")
    return "\n".join(lines)


# ============================================================
# ЭКСПОРТ В CSV
# ============================================================
async def export_to_csv(
    campaign_id: int,
    only_confirmed: bool = True,
) -> Optional[bytes]:
    """
    Возвращает CSV-байты для отправки файлом.

    Колонки: user_id, telegram_id, username, first_name,
             status, checked_at, confirmed_at
    """
    async with async_session() as session:
        campaign = (await session.execute(
            select(SubscriptionCampaign).where(SubscriptionCampaign.id == campaign_id)
        )).scalar_one_or_none()

        if campaign is None:
            return None

        q = (
            select(SubscriptionEvent, User)
            .join(User, User.id == SubscriptionEvent.user_id)
            .where(SubscriptionEvent.campaign_id == campaign_id)
        )
        if only_confirmed:
            q = q.where(SubscriptionEvent.status == "confirmed")
        q = q.order_by(SubscriptionEvent.id)

        rows = (await session.execute(q)).all()

    # CSV
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "user_id", "telegram_id", "username", "first_name",
        "status", "checked_at", "confirmed_at",
    ])
    for ev, u in rows:
        writer.writerow([
            u.id,
            u.telegram_id,
            u.username or "",
            u.first_name or "",
            ev.status,
            ev.checked_at.isoformat() if ev.checked_at else "",
            ev.confirmed_at.isoformat() if ev.confirmed_at else "",
        ])

    return buf.getvalue().encode("utf-8-sig")  # BOM для Excel