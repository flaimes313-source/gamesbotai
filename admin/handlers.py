from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message
from sqlalchemy import func, select

from admin.subscriptions_wizard import start_wizard
from bot.keyboards.admin import (
    admin_menu_kb,
    ads_menu_kb,
    flags_menu_kb,
    promos_menu_kb,
    subs_back_kb,
    subs_campaign_card_kb,
    subs_edit_cancel_kb,
    subs_edit_kb,
    subs_menu_kb,
    subs_subscribers_kb,
)
from config import config
from database.connection import async_session
from database.models import (
    AdvertisingCampaign,
    Payment,
    Promocode,
    SubscriptionCampaign,
    SupportTicket,
    User,
    Whitelist,
)
from services.advertising.reports import ads_report, format_ads_report
from services.analytics.funnel import format_funnel, get_funnel
from services.experiments_report import ab_photo_prompt_report, format_ab_report
from services.feature_flags import DEFAULTS as DEFAULT_FLAGS
from services.feature_flags import get_all_flags, is_enabled, set_flag
from services.metrics import chats_stats, full_stats
from services.subscriptions.reports import (
    export_to_csv,
    format_campaign_card,
    format_daily_breakdown,
    format_subscribers_list,
    get_campaign_daily_breakdown,
    get_campaign_stats,
    get_campaign_subscribers,
)
from services.whitelist import add_to_whitelist, remove_from_whitelist
from utils.logging import get_logger

router = Router()
logger = get_logger(__name__)

ADMIN_STATE: dict[int, dict] = {}
SUBS_PAGE_SIZE = 50


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
    try:
        await callback.message.edit_text(
            "🛠 <b>Админ-панель</b>",
            reply_markup=admin_menu_kb(),
        )
    except Exception:
        await callback.message.answer(
            "🛠 <b>Админ-панель</b>",
            reply_markup=admin_menu_kb(),
        )


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
        f"💬 Chats: {stats['chats_total']}\n"
        f"🧪 Tests: {stats['tests']}\n\n"
        f"💰 PRO revenue: {stats['pro_revenue']:.2f} ₽"
    )
    await callback.message.answer(text)


# ============================================================
# ЧАТЫ
# ============================================================
@router.callback_query(F.data == "adm_chats")
async def cb_admin_chats(callback: CallbackQuery):
    await _safe_answer(callback)
    if not _is_admin(callback.from_user.id):
        return
    try:
        stats = await chats_stats(days=7)
    except Exception:
        logger.exception("Chats stats failed")
        await callback.message.answer("❌ Не удалось получить статистику.")
        return

    lines = [
        f"💬 <b>Статистика чатов (за {stats['days']} дней)</b>\n",
        f"📊 Всего чатов: <b>{stats['total_chats']}</b>",
        f"🔥 Активных: <b>{stats['active_chats']}</b>",
        f"✉️ Сообщений: <b>{stats['total_messages']}</b>",
        f"📈 Средне: <b>{stats['avg_messages']}</b> сообщений на активный чат\n",
        "🏆 <b>Топ-5 активных диалогов:</b>",
    ]
    for t in stats["top"]:
        lines.append(f"#{t['chat_id']}: {t['user1']} ↔ {t['user2']} — {t['count']} сообщений")
    if not stats["top"]:
        lines.append("<i>Нет активных диалогов</i>")
    await callback.message.answer("\n".join(lines))


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
# A/B ТЕСТЫ
# ============================================================
@router.callback_query(F.data == "adm_ab")
async def cb_ab(callback: CallbackQuery):
    await _safe_answer(callback)
    if not _is_admin(callback.from_user.id):
        return
    try:
        report = await ab_photo_prompt_report(days=30)
        await callback.message.answer(format_ab_report(report))
    except Exception:
        logger.exception("AB report failed")
        await callback.message.answer("❌ Не удалось построить отчёт.")


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
# WHITELIST
# ============================================================
@router.callback_query(F.data == "adm_wl")
async def cb_wl(callback: CallbackQuery):
    await _safe_answer(callback)
    if not _is_admin(callback.from_user.id):
        return

    async with async_session() as session:
        rows = (await session.execute(
            select(Whitelist).order_by(Whitelist.id.desc()).limit(30)
        )).scalars().all()

    lines = ["⭐ <b>Whitelist</b>\n"]
    if not rows:
        lines.append("Пусто.")
    else:
        for w in rows:
            exp = w.expires_at.strftime("%Y-%m-%d") if w.expires_at else "∞"
            lines.append(f"• {w.user_id} — {w.reason or '—'} (до {exp})")

    lines.append("\nКоманды:")
    lines.append("<code>/wl_add &lt;tg_id&gt; [причина]</code>")
    lines.append("<code>/wl_remove &lt;tg_id&gt;</code>")
    await callback.message.answer("\n".join(lines))


@router.message(Command("wl_add"))
async def cmd_wl_add(message: Message):
    if not _is_admin(message.from_user.id):
        return
    parts = message.text.split(maxsplit=2)
    if len(parts) < 2:
        await message.answer("Формат: <code>/wl_add &lt;tg_id&gt; [причина]</code>")
        return
    try:
        tg_id = int(parts[1])
    except ValueError:
        await message.answer("ID должен быть числом.")
        return
    reason = parts[2] if len(parts) > 2 else None
    await add_to_whitelist(tg_id, reason=reason, added_by=message.from_user.id)
    await message.answer(
        f"✅ <b>{tg_id}</b> добавлен в whitelist.\n\n"
        f"<b>Что это даёт:</b>\n"
        f"• ♾ Безлимит AI-анализов\n"
        f"• 🚫 Пропуск обязательных подписок\n"
        f"• 🚫 Без рекламы\n\n"
        f"Причина: {reason or '—'}"
    )


@router.message(Command("wl_remove"))
async def cmd_wl_remove(message: Message):
    if not _is_admin(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("Формат: <code>/wl_remove &lt;tg_id&gt;</code>")
        return
    try:
        tg_id = int(parts[1])
    except ValueError:
        await message.answer("ID должен быть числом.")
        return
    await remove_from_whitelist(tg_id)
    await message.answer(f"✅ <b>{tg_id}</b> удалён из whitelist.")


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
            c.ended_at = datetime.now(timezone.utc)
        await session.commit()
    await callback.message.answer(f"🚨 Остановлено кампаний: {len(rows)}")


@router.callback_query(F.data == "adm_ads_report")
async def cb_ads_report(callback: CallbackQuery):
    await _safe_answer(callback)
    if not _is_admin(callback.from_user.id):
        return
    try:
        report = await ads_report(days=30)
        await callback.message.answer(format_ads_report(report))
    except Exception:
        logger.exception("Ads report failed")
        await callback.message.answer("❌ Не удалось получить отчёт.")


# ============================================================
# ПОДПИСКИ
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

    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    kb_rows = []
    lines = ["📋 <b>Кампании подписок</b>\n"]
    for c in rows:
        status_icon = "🟢" if c.is_active else "🔴"
        lines.append(
            f"{status_icon} #{c.id} <b>{c.name}</b>\n"
            f"   канал: {c.channel_username or '—'}, "
            f"подписок: {c.confirmed_subscribers}/{c.subscriber_limit or '∞'}"
        )
        kb_rows.append([InlineKeyboardButton(
            text=f"#{c.id} {c.name[:40]}",
            callback_data=f"subs_card_{c.id}",
        )])
    kb_rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="adm_subs")])

    try:
        await callback.message.answer(
            "\n".join(lines),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows),
        )
    except Exception:
        await callback.message.answer("\n".join(lines))


@router.callback_query(F.data == "subs_summary")
async def cb_subs_summary(callback: CallbackQuery):
    await _safe_answer(callback)
    if not _is_admin(callback.from_user.id):
        return

    async with async_session() as session:
        rows = (await session.execute(
            select(SubscriptionCampaign).order_by(SubscriptionCampaign.id.desc())
        )).scalars().all()

    if not rows:
        await callback.message.answer("Кампаний нет.")
        return

    total_confirmed = 0
    total_cost = 0.0

    lines = ["📊 <b>СВОДКА ПО ВСЕМ КАМПАНИЯМ</b>\n"]
    for c in rows:
        price = float(c.price_per_subscription or 0)
        cost = price * c.confirmed_subscribers
        total_confirmed += c.confirmed_subscribers
        total_cost += cost

        status_icon = "🟢" if c.is_active else "🔴"
        lines.append(
            f"{status_icon} <b>{c.name}</b>\n"
            f"   подписок: {c.confirmed_subscribers} × {price:.0f} ₽ = <b>{cost:.0f} ₽</b>"
        )

    lines.append("")
    lines.append("━━━━━━━━━━━━━━━━━━")
    lines.append(
        f"<b>Итого: {total_confirmed} подписчиков, {total_cost:.0f} ₽</b>"
    )

    await callback.message.answer(
        "\n".join(lines),
        reply_markup=subs_back_kb(),
    )


# ============================================================
# КАРТОЧКА КАМПАНИИ
# ============================================================
@router.callback_query(F.data.startswith("subs_card_"))
async def cb_subs_card(callback: CallbackQuery):
    await _safe_answer(callback)
    if not _is_admin(callback.from_user.id):
        return

    try:
        campaign_id = int(callback.data.replace("subs_card_", ""))
    except ValueError:
        await callback.message.answer("Некорректный ID.")
        return

    stats = await get_campaign_stats(campaign_id)
    if stats is None:
        await callback.message.answer("Кампания не найдена.")
        return

    text = format_campaign_card(stats)
    kb = subs_campaign_card_kb(campaign_id, stats["campaign"]["is_active"])

    try:
        await callback.message.edit_text(text, reply_markup=kb)
    except Exception:
        await callback.message.answer(text, reply_markup=kb)


# ============================================================
# ВОЗОБНОВЛЕНИЕ КАМПАНИИ
# ============================================================
@router.callback_query(F.data.startswith("subs_resume_"))
async def cb_subs_resume(callback: CallbackQuery):
    await _safe_answer(callback, "Запускаю…")
    if not _is_admin(callback.from_user.id):
        return

    try:
        campaign_id = int(callback.data.replace("subs_resume_", ""))
    except ValueError:
        await callback.message.answer("Некорректный ID.")
        return

    async with async_session() as session:
        c = (await session.execute(
            select(SubscriptionCampaign).where(SubscriptionCampaign.id == campaign_id)
        )).scalar_one_or_none()

        if c is None:
            await callback.message.answer("Кампания не найдена.")
            return

        c.is_active = True
        c.status = "active"
        c.ended_at = None
        # started_at НЕ трогаем — сохраняем историю первого запуска
        await session.commit()

    stats = await get_campaign_stats(campaign_id)
    if stats:
        text = format_campaign_card(stats)
        kb = subs_campaign_card_kb(campaign_id, stats["campaign"]["is_active"])
        try:
            await callback.message.edit_text(text, reply_markup=kb)
        except Exception:
            await callback.message.answer(text, reply_markup=kb)


# ============================================================
# ПОДМЕНЮ РЕДАКТИРОВАНИЯ
# ============================================================
@router.callback_query(F.data.startswith("subs_edit_") & ~F.data.startswith("subs_edit_price_") & ~F.data.startswith("subs_edit_limit_") & ~F.data.startswith("subs_edit_budget_"))
async def cb_subs_edit_menu(callback: CallbackQuery):
    """Открывает подменю редактирования."""
    await _safe_answer(callback)
    if not _is_admin(callback.from_user.id):
        return

    try:
        campaign_id = int(callback.data.replace("subs_edit_", ""))
    except ValueError:
        await callback.message.answer("Некорректный ID.")
        return

    async with async_session() as session:
        c = (await session.execute(
            select(SubscriptionCampaign).where(SubscriptionCampaign.id == campaign_id)
        )).scalar_one_or_none()

    if c is None:
        await callback.message.answer("Кампания не найдена.")
        return

    text = (
        f"✏️ <b>РЕДАКТИРОВАНИЕ КАМПАНИИ #{c.id}</b>\n\n"
        f"📢 {c.name}\n\n"
        f"💰 Цена за подписчика: <b>{float(c.price_per_subscription or 0):.0f} ₽</b>\n"
        f"👥 Лимит подписчиков: <b>{c.subscriber_limit or '∞'}</b>\n"
        f"💵 Бюджет: <b>{float(c.budget or 0):.0f} ₽</b>\n\n"
        f"Что изменить?"
    )

    try:
        await callback.message.edit_text(text, reply_markup=subs_edit_kb(campaign_id))
    except Exception:
        await callback.message.answer(text, reply_markup=subs_edit_kb(campaign_id))


# ============================================================
# FSM: НАЧАЛО РЕДАКТИРОВАНИЯ
# ============================================================
async def _start_edit(
    callback: CallbackQuery,
    field: str,
    prompt: str,
    campaign_id: int,
) -> None:
    """Общая логика старта FSM-ввода."""
    ADMIN_STATE[callback.from_user.id] = {
        "action": f"subs_edit_{field}",
        "campaign_id": campaign_id,
    }
    await _safe_answer(callback)
    await callback.message.answer(
        prompt,
        reply_markup=subs_edit_cancel_kb(campaign_id),
    )


@router.callback_query(F.data.startswith("subs_edit_price_"))
async def cb_subs_edit_price(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id):
        return
    try:
        campaign_id = int(callback.data.replace("subs_edit_price_", ""))
    except ValueError:
        await callback.answer("Некорректный ID.")
        return

    await _start_edit(
        callback,
        field="price",
        prompt=(
            "💰 <b>Изменение цены</b>\n\n"
            "Отправь новую цену за подписчика в рублях (можно с копейками).\n\n"
            "Пример: <code>15</code> или <code>12.5</code>"
        ),
        campaign_id=campaign_id,
    )


@router.callback_query(F.data.startswith("subs_edit_limit_"))
async def cb_subs_edit_limit(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id):
        return
    try:
        campaign_id = int(callback.data.replace("subs_edit_limit_", ""))
    except ValueError:
        await callback.answer("Некорректный ID.")
        return

    await _start_edit(
        callback,
        field="limit",
        prompt=(
            "👥 <b>Изменение лимита подписчиков</b>\n\n"
            "Отправь новое максимальное число подписчиков.\n\n"
            "Пример: <code>500</code>\n"
            "Чтобы убрать лимит — отправь <code>0</code>"
        ),
        campaign_id=campaign_id,
    )


@router.callback_query(F.data.startswith("subs_edit_budget_"))
async def cb_subs_edit_budget(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id):
        return
    try:
        campaign_id = int(callback.data.replace("subs_edit_budget_", ""))
    except ValueError:
        await callback.answer("Некорректный ID.")
        return

    await _start_edit(
        callback,
        field="budget",
        prompt=(
            "💵 <b>Изменение бюджета</b>\n\n"
            "Отправь новый бюджет кампании в рублях.\n\n"
            "Пример: <code>5000</code>\n"
            "Чтобы убрать лимит бюджета — отправь <code>0</code>"
        ),
        campaign_id=campaign_id,
    )


# ============================================================
# FSM: ПРИЁМ ЗНАЧЕНИЯ
# ============================================================
@router.message(
    F.text,
    lambda m: ADMIN_STATE.get(m.from_user.id, {}).get("action", "").startswith("subs_edit_")
)
async def subs_edit_input(message: Message):
    """
    Принимает число для цены / лимита / бюджета.
    ВАЖНО: этот хендлер должен идти ДО admin_input!
    """
    if not _is_admin(message.from_user.id):
        return

    state = ADMIN_STATE.get(message.from_user.id)
    if not state:
        return

    action = state.get("action", "")
    campaign_id = state.get("campaign_id")
    if not action or not campaign_id:
        ADMIN_STATE.pop(message.from_user.id, None)
        return

    text = (message.text or "").strip().replace(",", ".")
    try:
        value = float(text)
    except ValueError:
        await message.answer(
            "❌ Не похоже на число. Попробуй ещё раз или нажми «Отмена»."
        )
        return

    if value < 0:
        await message.answer("❌ Значение не может быть отрицательным.")
        return

    field = action.replace("subs_edit_", "")  # price / limit / budget

    async with async_session() as session:
        c = (await session.execute(
            select(SubscriptionCampaign).where(SubscriptionCampaign.id == campaign_id)
        )).scalar_one_or_none()

        if c is None:
            ADMIN_STATE.pop(message.from_user.id, None)
            await message.answer("Кампания не найдена.")
            return

        if field == "price":
            c.price_per_subscription = value
            field_label = f"цена = <b>{value:.0f} ₽</b>"
        elif field == "limit":
            c.subscriber_limit = int(value)
            field_label = f"лимит = <b>{int(value) if value > 0 else '∞'}</b>"
        elif field == "budget":
            c.budget = value
            field_label = f"бюджет = <b>{value:.0f} ₽</b>"
        else:
            ADMIN_STATE.pop(message.from_user.id, None)
            await message.answer("Неизвестное поле.")
            return

        await session.commit()

    ADMIN_STATE.pop(message.from_user.id, None)

    # Показываем обновлённую карточку
    stats = await get_campaign_stats(campaign_id)
    if stats:
        text_out = (
            f"✅ <b>Сохранено</b>\n\n"
            f"Кампания #{campaign_id}: {field_label}\n\n"
            + format_campaign_card(stats)
        )
        kb = subs_campaign_card_kb(campaign_id, stats["campaign"]["is_active"])
        try:
            await message.answer(text_out, reply_markup=kb)
        except Exception:
            await message.answer(text_out)


# ============================================================
# ПОДПИСЧИКИ
# ============================================================
@router.callback_query(F.data.startswith("subs_subs_"))
async def cb_subs_subscribers(callback: CallbackQuery):
    await _safe_answer(callback)
    if not _is_admin(callback.from_user.id):
        return

    data = callback.data.replace("subs_subs_", "")
    page = 1
    if "_p" in data:
        cid_str, p_str = data.split("_p", 1)
        try:
            page = max(1, int(p_str))
        except ValueError:
            page = 1
        campaign_id = int(cid_str)
    else:
        campaign_id = int(data)

    stats = await get_campaign_stats(campaign_id)
    if stats is None:
        await callback.message.answer("Кампания не найдена.")
        return

    confirmed_total = stats["counts"]["confirmed"]
    offset = (page - 1) * SUBS_PAGE_SIZE

    subscribers = await get_campaign_subscribers(
        campaign_id,
        limit=SUBS_PAGE_SIZE,
        offset=offset,
        only_confirmed=True,
    )

    has_next = (offset + SUBS_PAGE_SIZE) < confirmed_total

    text = format_subscribers_list(
        subscribers,
        total=confirmed_total,
        page=page,
        per_page=SUBS_PAGE_SIZE,
        only_confirmed=True,
    )
    text += f"\n\nСтраница {page}"
    if has_next:
        text += " (есть ещё)"

    kb = subs_subscribers_kb(campaign_id, page, has_next)

    try:
        await callback.message.edit_text(text, reply_markup=kb)
    except Exception:
        await callback.message.answer(text, reply_markup=kb)


@router.callback_query(F.data.startswith("subs_daily_"))
async def cb_subs_daily(callback: CallbackQuery):
    await _safe_answer(callback)
    if not _is_admin(callback.from_user.id):
        return

    try:
        campaign_id = int(callback.data.replace("subs_daily_", ""))
    except ValueError:
        await callback.message.answer("Некорректный ID.")
        return

    stats = await get_campaign_stats(campaign_id)
    if stats is None:
        await callback.message.answer("Кампания не найдена.")
        return

    breakdown = await get_campaign_daily_breakdown(campaign_id)

    text = format_daily_breakdown(
        breakdown,
        campaign_name=stats["campaign"]["name"],
        price=stats["campaign"]["price_per_subscription"],
    )

    try:
        await callback.message.edit_text(text, reply_markup=subs_back_kb())
    except Exception:
        await callback.message.answer(text, reply_markup=subs_back_kb())


@router.callback_query(F.data.startswith("subs_export_"))
async def cb_subs_export(callback: CallbackQuery):
    await _safe_answer(callback, "Готовлю CSV…")
    if not _is_admin(callback.from_user.id):
        return

    try:
        campaign_id = int(callback.data.replace("subs_export_", ""))
    except ValueError:
        await callback.message.answer("Некорректный ID.")
        return

    stats = await get_campaign_stats(campaign_id)
    if stats is None:
        await callback.message.answer("Кампания не найдена.")
        return

    csv_bytes = await export_to_csv(campaign_id, only_confirmed=True)
    if not csv_bytes:
        await callback.message.answer("Не удалось подготовить файл.")
        return

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    filename = f"campaign_{campaign_id}_{today}.csv"

    try:
        await callback.message.answer_document(
            BufferedInputFile(csv_bytes, filename=filename),
            caption=(
                f"📤 <b>Экспорт кампании #{campaign_id}</b>\n"
                f"{stats['campaign']['name']}\n"
                f"Подписчиков: <b>{stats['counts']['confirmed']}</b>\n"
                f"Стоимость: <b>{stats['money']['total_cost']:.0f} ₽</b>"
            ),
        )
    except Exception:
        logger.exception("[SUBS] export send failed")
        await callback.message.answer("❌ Не удалось отправить файл.")


@router.callback_query(F.data.startswith("subs_stop_"))
async def cb_subs_stop(callback: CallbackQuery):
    await _safe_answer(callback, "Останавливаю…")
    if not _is_admin(callback.from_user.id):
        return

    try:
        campaign_id = int(callback.data.replace("subs_stop_", ""))
    except ValueError:
        await callback.message.answer("Некорректный ID.")
        return

    async with async_session() as session:
        c = (await session.execute(
            select(SubscriptionCampaign).where(SubscriptionCampaign.id == campaign_id)
        )).scalar_one_or_none()

        if c is None:
            await callback.message.answer("Кампания не найдена.")
            return

        c.is_active = False
        c.status = "stopped"
        c.ended_at = datetime.now(timezone.utc)
        await session.commit()

    stats = await get_campaign_stats(campaign_id)
    if stats:
        text = format_campaign_card(stats)
        kb = subs_campaign_card_kb(campaign_id, stats["campaign"]["is_active"])
        try:
            await callback.message.edit_text(text, reply_markup=kb)
        except Exception:
            await callback.message.answer(text, reply_markup=kb)


@router.callback_query(F.data == "subs_new")
async def cb_subs_new(callback: CallbackQuery, state: FSMContext):
    await _safe_answer(callback)
    if not _is_admin(callback.from_user.id):
        return
    await start_wizard(callback, state)


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
            c.ended_at = datetime.now(timezone.utc)
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
@router.callback_query(F.data == "adm_flags")
async def cb_flags(callback: CallbackQuery):
    await _safe_answer(callback)
    if not _is_admin(callback.from_user.id):
        return
    flags = await get_all_flags()
    await callback.message.answer(
        "⚙️ <b>Feature flags</b>\n\n"
        "Нажми на любой флаг, чтобы переключить. "
        "Изменения применяются сразу, без перезапуска бота.",
        reply_markup=flags_menu_kb(flags),
    )


@router.callback_query(F.data.startswith("flag_toggle_"))
async def cb_flag_toggle(callback: CallbackQuery):
    await _safe_answer(callback)
    if not _is_admin(callback.from_user.id):
        return
    key = callback.data.replace("flag_toggle_", "")
    current = await is_enabled(key, default=DEFAULT_FLAGS.get(key, False))
    await set_flag(key, not current)
    flags = await get_all_flags()
    try:
        await callback.message.edit_reply_markup(reply_markup=flags_menu_kb(flags))
    except TelegramBadRequest:
        await callback.message.answer("⚙️ <b>Feature flags</b>", reply_markup=flags_menu_kb(flags))


# ============================================================
# ПЛАТЕЖИ
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


# ============================================================
# ПОДДЕРЖКА
# ============================================================
@router.callback_query(F.data == "adm_support")
async def cb_support(callback: CallbackQuery):
    await _safe_answer(callback)
    if not _is_admin(callback.from_user.id):
        return
    async with async_session() as session:
        tickets = (await session.execute(
            select(SupportTicket)
            .where(SupportTicket.status == "open")
            .order_by(SupportTicket.id.desc())
            .limit(20)
        )).scalars().all()
    if not tickets:
        await callback.message.answer("🆘 Открытых тикетов нет.")
        return
    lines = ["🆘 <b>Открытые тикеты</b>\n"]
    for t in tickets:
        lines.append(
            f"#{t.id} [user_id={t.user_id}]\n"
            f"   {t.message[:200]}\n"
        )
    lines.append("\nЧтобы ответить: <code>/reply &lt;ticket_id&gt; текст</code>")
    await callback.message.answer("\n".join(lines))


@router.message(Command("reply"))
async def cmd_reply(message: Message):
    if not _is_admin(message.from_user.id):
        return
    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        await message.answer("Формат: <code>/reply &lt;ticket_id&gt; текст</code>")
        return
    try:
        ticket_id = int(parts[1])
    except ValueError:
        await message.answer("ID должен быть числом.")
        return
    reply_text = parts[2]
    async with async_session() as session:
        ticket = (await session.execute(
            select(SupportTicket).where(SupportTicket.id == ticket_id)
        )).scalar_one_or_none()
        if ticket is None:
            await message.answer("Тикет не найден.")
            return
        ticket.admin_reply = reply_text
        ticket.status = "closed"
        ticket.closed_at = datetime.now(timezone.utc)
        user = (await session.execute(
            select(User).where(User.id == ticket.user_id)
        )).scalar_one_or_none()
        await session.commit()
    if user:
        try:
            await message.bot.send_message(
                user.telegram_id,
                f"💬 <b>Ответ поддержки по тикету #{ticket_id}</b>\n\n{reply_text}"
            )
            await message.answer(f"✅ Ответ отправлен в тикет #{ticket_id}.")
        except Exception:
            logger.exception("Failed to send reply")
            await message.answer("❌ Не удалось доставить ответ.")


# ============================================================
# ВРЕМЕННЫЕ КОМАНДЫ
# ============================================================
@router.message(Command("grant_pro"))
async def cmd_grant_pro(message: Message):
    if not _is_admin(message.from_user.id):
        return
    parts = message.text.split(maxsplit=3)
    if len(parts) < 3:
        await message.answer("Формат: /grant_pro <tg_id> <days> [reason]")
        return
    try:
        tg_id = int(parts[1])
        days = int(parts[2])
    except ValueError:
        await message.answer("tg_id и days — числа")
        return
    reason = parts[3] if len(parts) > 3 else "manual"
    async with async_session() as session:
        user = (await session.execute(
            select(User).where(User.telegram_id == tg_id)
        )).scalar_one_or_none()
    if user is None:
        await message.answer("Юзер не найден")
        return
    from services.engagement.rewards import grant_pro_days
    ok = await grant_pro_days(user.id, days, reason)
    await message.answer(
        f"{'✅' if ok else '❌'} user={user.id} tg={tg_id} PRO+{days}d ({reason})"
    )


@router.message(Command("fake_refs"))
async def cmd_fake_refs(message: Message):
    if not _is_admin(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("Формат: /fake_refs <count>")
        return
    try:
        count = int(parts[1])
    except ValueError:
        await message.answer("count — число")
        return
    if count < 1 or count > 50:
        await message.answer("count: 1-50")
        return

    import random
    from services.engagement.referrals import on_referred_user_analyzed

    async with async_session() as session:
        me = (await session.execute(
            select(User).where(User.telegram_id == message.from_user.id)
        )).scalar_one_or_none()

    if me is None:
        await message.answer("Сначала отправь фото")
        return

    created = 0
    for i in range(count):
        async with async_session() as session:
            while True:
                fake_tg = random.randint(10_000_000_000, 99_999_999_999)
                exists = (await session.execute(
                    select(User).where(User.telegram_id == fake_tg)
                )).scalar_one_or_none()
                if exists is None:
                    break
            fake = User(
                telegram_id=fake_tg,
                username=f"fake_{fake_tg % 10000}",
                first_name=f"Тест {fake_tg % 100}",
                referrer_id=me.id,
                timezone="Europe/Moscow",
            )
            session.add(fake)
            await session.commit()
            await session.refresh(fake)
            fake_id = fake.id
        await on_referred_user_analyzed(fake_id)
        created += 1

    await message.answer(f"✅ Создано {created} фиктивных рефералов")


# ============================================================
# ВВОД ТЕКСТА ОТ АДМИНА (ADS / PROMOS)
# ВАЖНО: идёт ПОСЛЕ subs_edit_input!
# ============================================================
@router.message(F.text, lambda m: m.from_user.id in ADMIN_STATE)
async def admin_input(message: Message):
    if not _is_admin(message.from_user.id):
        return
    state = ADMIN_STATE.get(message.from_user.id)
    if not state:
        return
    action = state.get("action")

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

    ADMIN_STATE.pop(message.from_user.id, None)
    await message.answer("Неизвестная команда.")