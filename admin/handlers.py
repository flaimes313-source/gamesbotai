from datetime import datetime
from typing import Optional

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy import func, select

from bot.keyboards.admin import (
    admin_menu_kb,
    ads_menu_kb,
    flags_menu_kb,
    promos_menu_kb,
    subs_menu_kb,
)
from config import config
from database.connection import async_session
from database.models import (
    AdvertisingCampaign,
    FeatureFlag,
    Payment,
    Promocode,
    SubscriptionCampaign,
    User,
)
from services.analytics.funnel import format_funnel, get_funnel
from services.metrics import full_stats
from utils.logging import get_logger

router = Router()
logger = get_logger(__name__)


# Состояние ввода админа: admin_tg → {"action": "...", "data": {...}}
ADMIN_STATE: dict[int, dict] = {}


def _is_admin(telegram_id: int) -> bool:
    return telegram_id in config.ADMIN_IDS


async def _safe_answer(callback: CallbackQuery, text: str | None = None) -> None:
    try:
        await callback.answer(text)
    except TelegramBadRequest as e:
        logger.warning(f"callback.answer failed (non-critical): {e}")


# ============================================================
# ROOT
# ============================================================
@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if not _is_admin(message.from_user.id):
        return
    await message.answer("🛠 <b>Админ-панель</b>", reply_markup=admin_menu_kb())


@router.callback_query(F.data == "adm_back")
async def cb_back(callback: CallbackQuery):
    await _safe_answer(callback)
    if not _is_admin(callback.from_user.id):
        return
    await callback.message.edit_text("🛠 <b>Админ-панель</b>", reply_markup=admin_menu_kb())


# ============================================================
# СТАТИСТИКА
# ============================================================
@router.callback_query(F.data == "adm_stats")
async def cb_stats(callback: CallbackQuery):
    await _safe_answer(callback)
    if not _is_admin(callback.from_user.id):
        return

    try:
        stats = await full_stats()
    except Exception:
        logger.exception("Stats failed")
        await callback.message.answer("❌ Не удалось получить статистику.")
        return

    text = (
        f"📊 <b>BOT STATS</b>\n\n"
        f"👥 Users: {stats['users']}\n"
        f"📈 DAU: {stats['dau']}\n"
        f"🆕 New today: {stats['new']}\n\n"
        f"📸 Analyses: {stats['analyses']}\n"
        f"🎯 Matches: {stats['matches']}\n"
        f"💬 Messages: {stats['messages']}\n"
        f"🧪 Tests: {stats['tests']}\n\n"
        f"💰 PRO revenue: {stats['pro_revenue']:.2f} ₽"
    )
    await callback.message.answer(text)


# ============================================================
# ВОРОНКА
# ============================================================
@router.callback_query(F.data == "adm_funnel")
async def cb_funnel(callback: CallbackQuery):
    await _safe_answer(callback)
    if not _is_admin(callback.from_user.id):
        return

    try:
        funnel = await get_funnel(days=30)
    except Exception:
        logger.exception("Funnel failed")
        await callback.message.answer("❌ Не удалось построить воронку.")
        return

    await callback.message.answer(format_funnel(funnel))


# ============================================================
# ПОЛЬЗОВАТЕЛИ
# ============================================================
@router.callback_query(F.data == "adm_users")
async def cb_users(callback: CallbackQuery):
    await _safe_answer(callback)
    if not _is_admin(callback.from_user.id):
        return

    async with async_session() as session:
        users = (await session.execute(
            select(User).order_by(User.id.desc()).limit(20)
        )).scalars().all()

    lines = ["👥 <b>Последние 20 пользователей</b>\n"]
    for u in users:
        lines.append(f"• {u.telegram_id} @{u.username or '—'} (game={u.participates_in_game})")
    await callback.message.answer("\n".join(lines))


# ============================================================
# РЕКЛАМА
# ============================================================
@router.callback_query(F.data == "adm_ads")
async def cb_ads(callback: CallbackQuery):
    await _safe_answer(callback)
    if not _is_admin(callback.from_user.id):
        return
    await callback.message.answer("📢 <b>Управление рекламой</b>", reply_markup=ads_menu_kb())


@router.callback_query(F.data == "ads_list")
async def cb_ads_list(callback: CallbackQuery):
    await _safe_answer(callback)
    if not _is_admin(callback.from_user.id):
        return

    async with async_session() as session:
        rows = (await session.execute(
            select(AdvertisingCampaign).order_by(AdvertisingCampaign.id.desc()).limit(20)
        )).scalars().all()

    if not rows:
        await callback.message.answer("Кампаний нет.")
        return

    lines = ["📋 <b>Рекламные кампании</b>\n"]
    for c in rows:
        lines.append(
            f"#{c.id} <b>{c.name}</b> [{c.status}]\n"
            f"   показов: {c.sent_count}/{c.impression_limit or '∞'}, кликов: {c.clicks}"
        )
    await callback.message.answer("\n".join(lines))


@router.callback_query(F.data == "ads_new")
async def cb_ads_new(callback: CallbackQuery):
    await _safe_answer(callback)
    if not _is_admin(callback.from_user.id):
        return

    ADMIN_STATE[callback.from_user.id] = {"action": "ads_new_step1"}
    await callback.message.answer(
        "➕ Новая рекламная кампания\n\n"
        "Отправь текст рекламы одним сообщением.\n"
        "Формат: <code>Название | Текст рекламы</code>"
    )


@router.callback_query(F.data == "ads_stop_all")
async def cb_ads_stop_all(callback: CallbackQuery):
    await _safe_answer(callback)
    if not _is_admin(callback.from_user.id):
        return

    async with async_session() as session:
        rows = (await session.execute(
            select(AdvertisingCampaign).where(AdvertisingCampaign.status == "active")
        )).scalars().all()
        for c in rows:
            c.status = "stopped"
            c.ended_at = datetime.utcnow()
        await session.commit()

    await callback.message.answer(f"🚨 Остановлено кампаний: {len(rows)}")


# ============================================================
# ОБЯЗАТЕЛЬНЫЕ ПОДПИСКИ
# ============================================================
@router.callback_query(F.data == "adm_subs")
async def cb_subs(callback: CallbackQuery):
    await _safe_answer(callback)
    if not _is_admin(callback.from_user.id):
        return
    await callback.message.answer("📣 <b>Обязательные подписки</b>", reply_markup=subs_menu_kb())


@router.callback_query(F.data == "subs_list")
async def cb_subs_list(callback: CallbackQuery):
    await _safe_answer(callback)
    if not _is_admin(callback.from_user.id):
        return

    async with async_session() as session:
        rows = (await session.execute(
            select(SubscriptionCampaign).order_by(SubscriptionCampaign.id.desc()).limit(20)
        )).scalars().all()

    if not rows:
        await callback.message.answer("Кампаний нет.")
        return

    lines = ["📋 <b>Кампании подписок</b>\n"]
    for c in rows:
        lines.append(
            f"#{c.id} <b>{c.name}</b> [{c.status}] active={c.is_active}\n"
            f"   канал: {c.channel_username or '—'}, подписок: {c.confirmed_subscribers}/{c.subscriber_limit or '∞'}"
        )
    await callback.message.answer("\n".join(lines))


@router.callback_query(F.data == "subs_new")
async def cb_subs_new(callback: CallbackQuery):
    await _safe_answer(callback)
    if not _is_admin(callback.from_user.id):
        return

    ADMIN_STATE[callback.from_user.id] = {"action": "subs_new_step1"}
    await callback.message.answer(
        "➕ Новая кампания подписок\n\n"
        "Отправь в формате:\n"
        "<code>Название | @channel_username | https://t.me/channel</code>\n\n"
        "⚠️ Бот должен быть админом канала!"
    )


@router.callback_query(F.data == "subs_stop_all")
async def cb_subs_stop_all(callback: CallbackQuery):
    await _safe_answer(callback)
    if not _is_admin(callback.from_user.id):
        return

    async with async_session() as session:
        rows = (await session.execute(
            select(SubscriptionCampaign).where(SubscriptionCampaign.is_active.is_(True))
        )).scalars().all()
        for c in rows:
            c.is_active = False
            c.status = "stopped"
            c.ended_at = datetime.utcnow()
        await session.commit()

    await callback.message.answer(f"🚨 Остановлено кампаний: {len(rows)}")


# ============================================================
# ПРОМОКОДЫ
# ============================================================
@router.callback_query(F.data == "adm_promos")
async def cb_promos(callback: CallbackQuery):
    await _safe_answer(callback)
    if not _is_admin(callback.from_user.id):
        return
    await callback.message.answer("🎟 <b>Промокоды</b>", reply_markup=promos_menu_kb())


@router.callback_query(F.data == "promos_list")
async def cb_promos_list(callback: CallbackQuery):
    await _safe_answer(callback)
    if not _is_admin(callback.from_user.id):
        return

    async with async_session() as session:
        rows = (await session.execute(
            select(Promocode).order_by(Promocode.id.desc()).limit(30)
        )).scalars().all()

    if not rows:
        await callback.message.answer("Промокодов нет.")
        return

    lines = ["🎟 <b>Промокоды</b>\n"]
    for p in rows:
        active = "✅" if p.is_active else "❌"
        lines.append(f"{active} <code>{p.code}</code> — {p.value} дн., {p.used_count}/{p.max_uses or '∞'}")
    await callback.message.answer("\n".join(lines))


@router.callback_query(F.data == "promos_new")
async def cb_promos_new(callback: CallbackQuery):
    await _safe_answer(callback)
    if not _is_admin(callback.from_user.id):
        return

    ADMIN_STATE[callback.from_user.id] = {"action": "promos_new_step1"}
    await callback.message.answer(
        "➕ Новый промокод\n\n"
        "Формат: <code>CODE | дней | макс.использований</code>\n"
        "Пример: <code>START50 | 30 | 100</code>"
    )


# ============================================================
# FEATURE FLAGS
# ============================================================
DEFAULT_FLAGS = {
    "bot_enabled": True,
    "ai_enabled": True,
    "matching_enabled": True,
    "referrals_enabled": True,
    "mandatory_subscriptions_enabled": False,
    "advertising_enabled": False,
    "premium_enabled": False,
    "daily_content_enabled": False,
    "friend_comparison_enabled": True,
    "player_search_enabled": True,
    "ai_message_helper_enabled": True,
}


async def _load_flags() -> dict[str, bool]:
    async with async_session() as session:
        rows = (await session.execute(select(FeatureFlag))).scalars().all()

    flags = dict(DEFAULT_FLAGS)
    for r in rows:
        flags[r.key] = r.enabled
    return flags


@router.callback_query(F.data == "adm_flags")
async def cb_flags(callback: CallbackQuery):
    await _safe_answer(callback)
    if not _is_admin(callback.from_user.id):
        return

    flags = await _load_flags()
    await callback.message.answer("⚙️ <b>Feature flags</b>", reply_markup=flags_menu_kb(flags))


@router.callback_query(F.data.startswith("flag_toggle_"))
async def cb_flag_toggle(callback: CallbackQuery):
    await _safe_answer(callback)
    if not _is_admin(callback.from_user.id):
        return

    key = callback.data.replace("flag_toggle_", "")

    async with async_session() as session:
        row = (await session.execute(
            select(FeatureFlag).where(FeatureFlag.key == key)
        )).scalar_one_or_none()

        if row is None:
            row = FeatureFlag(key=key, enabled=not DEFAULT_FLAGS.get(key, False))
            session.add(row)
        else:
            row.enabled = not row.enabled
        await session.commit()

    flags = await _load_flags()
    try:
        await callback.message.edit_reply_markup(reply_markup=flags_menu_kb(flags))
    except TelegramBadRequest:
        await callback.message.answer("⚙️ <b>Feature flags</b>", reply_markup=flags_menu_kb(flags))


# ============================================================
# ПЛАТЕЖИ / ПОДДЕРЖКА (заглушки)
# ============================================================
@router.callback_query(F.data == "adm_pay")
async def cb_pay(callback: CallbackQuery):
    await _safe_answer(callback)
    if not _is_admin(callback.from_user.id):
        return

    async with async_session() as session:
        total = (await session.execute(
            select(func.coalesce(func.sum(Payment.amount), 0)).where(Payment.status == "succeeded")
        )).scalar_one()
        cnt = (await session.execute(
            select(func.count(Payment.id)).where(Payment.status == "succeeded")
        )).scalar_one()

    await callback.message.answer(
        f"💰 <b>Платежи</b>\n\n"
        f"Успешных: {cnt}\n"
        f"Сумма: {float(total or 0):.2f} ₽"
    )


@router.callback_query(F.data == "adm_support")
async def cb_support(callback: CallbackQuery):
    await _safe_answer(callback)
    if not _is_admin(callback.from_user.id):
        return
    await callback.message.answer("🆘 Раздел поддержки в разработке.")


# ============================================================
# ВВОД ТЕКСТА ОТ АДМИНА (пошаговые диалоги)
# ============================================================
@router.message(F.text, lambda m: m.from_user.id in ADMIN_STATE)
async def admin_input(message: Message):
    if not _is_admin(message.from_user.id):
        return

    state = ADMIN_STATE.get(message.from_user.id)
    if not state:
        return

    action = state.get("action")

    # ---------- Реклама ----------
    if action == "ads_new_step1":
        parts = [p.strip() for p in message.text.split("|", 1)]
        if len(parts) != 2:
            await message.answer("❌ Формат: <code>Название | Текст рекламы</code>")
            return

        name, text = parts
        async with async_session() as session:
            c = AdvertisingCampaign(name=name, text=text, status="active")
            session.add(c)
            await session.commit()
            await session.refresh(c)

        ADMIN_STATE.pop(message.from_user.id, None)
        await message.answer(
            f"✅ Кампания #{c.id} создана и активирована.\n"
            f"Название: <b>{c.name}</b>\n"
            f"Текст: {c.text[:200]}"
        )
        return

    # ---------- Подписки ----------
    if action == "subs_new_step1":
        parts = [p.strip() for p in message.text.split("|")]
        if len(parts) != 3:
            await message.answer("❌ Формат: <code>Название | @channel | https://t.me/channel</code>")
            return

        name, channel_username, channel_link = parts
        channel_username_clean = channel_username.lstrip("@")

        async with async_session() as session:
            c = SubscriptionCampaign(
                name=name,
                status="active",
                is_active=True,
                channel_id=f"@{channel_username_clean}",
                channel_username=channel_username_clean,
                channel_link=channel_link,
                price_per_subscription=2.0,
                subscriber_limit=1000,
                budget=2000,
                started_at=datetime.utcnow(),
            )
            session.add(c)
            await session.commit()
            await session.refresh(c)

        ADMIN_STATE.pop(message.from_user.id, None)
        await message.answer(
            f"✅ Кампания #{c.id} создана.\n"
            f"Канал: {channel_link}"
        )
        return

    # ---------- Промокоды ----------
    if action == "promos_new_step1":
        parts = [p.strip() for p in message.text.split("|")]
        if len(parts) != 3:
            await message.answer("❌ Формат: <code>CODE | дней | макс</code>")
            return

        try:
            code = parts[0].upper()
            days = int(parts[1])
            max_uses = int(parts[2])
        except ValueError:
            await message.answer("❌ Дни и макс — числа.")
            return

        async with async_session() as session:
            exists = (await session.execute(
                select(Promocode).where(Promocode.code == code)
            )).scalar_one_or_none()

            if exists:
                await message.answer("❌ Такой промокод уже есть.")
                return

            p = Promocode(code=code, type="pro_days", value=days, max_uses=max_uses, is_active=True)
            session.add(p)
            await session.commit()

        ADMIN_STATE.pop(message.from_user.id, None)
        await message.answer(f"✅ Промокод <code>{code}</code> создан ({days} дней, макс {max_uses}).")
        return

    # ---------- Неизвестная команда ----------
    ADMIN_STATE.pop(message.from_user.id, None)
    await message.answer("Неизвестная команда.")