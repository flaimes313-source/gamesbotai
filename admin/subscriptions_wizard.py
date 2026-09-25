"""
FSM-мастер создания кампании обязательной подписки.

Порядок шагов:
1. Ссылка / @username канала.
2. Название (автоматически или вручную).
3. Цена за подписчика (₽).
4. Лимит подписчиков.
5. Бюджет кампании (₽).
6. Финальное подтверждение → создание.
"""

from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select

from config import config
from database.connection import async_session
from database.models import SubscriptionCampaign
from services.subscriptions.channel_resolver import (
    can_check_subscription,
    resolve_channel,
)
from services.subscriptions.link_parser import parse_channel_link
from utils.logging import get_logger

router = Router()
logger = get_logger(__name__)


def _is_admin(telegram_id: int) -> bool:
    return telegram_id in config.ADMIN_IDS


# ============================================================
# FSM
# ============================================================
class SubsWizard(StatesGroup):
    waiting_link = State()
    waiting_title_manual = State()
    waiting_price = State()
    waiting_limit = State()
    waiting_budget = State()
    confirming = State()


# ============================================================
# Клавиатуры
# ============================================================
def _cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="subs_wiz_cancel")],
        ]
    )


def _number_kb(prefix: str) -> InlineKeyboardMarkup:
    """
    Клавиатура для числовых шагов: только «Отмена».
    Юзер вводит число текстом.
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="subs_wiz_cancel")],
        ]
    )


def _confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Создать кампанию", callback_data="subs_wiz_confirm")],
            [InlineKeyboardButton(text="✏️ Изменить название", callback_data="subs_wiz_edit_title")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="subs_wiz_cancel")],
        ]
    )


# ============================================================
# ТОЧКА ВХОДА
# ============================================================
async def start_wizard(callback: CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return

    await state.set_state(SubsWizard.waiting_link)
    await callback.message.answer(
        "📣 <b>Новая кампания подписок</b>\n\n"
        "Шаг 1. Отправь <b>ссылку</b> или <b>@username</b> канала.\n\n"
        "Подойдут форматы:\n"
        "• <code>https://t.me/your_channel</code>\n"
        "• <code>@your_channel</code>\n"
        "• <code>your_channel</code>\n\n"
        "⚠️ Бот должен быть <b>админом</b> этого канала, "
        "иначе не сможет проверять подписки.",
        reply_markup=_cancel_kb(),
    )


# ============================================================
# ШАГ 1: ССЫЛКА
# ============================================================
@router.message(SubsWizard.waiting_link)
async def process_link(message: Message, state: FSMContext):
    if not _is_admin(message.from_user.id):
        return

    text = (message.text or "").strip()
    parsed = parse_channel_link(text)

    if parsed is None:
        await message.answer(
            "❌ Не удалось распознать ссылку.\n\n"
            "Попробуй ещё раз: <code>https://t.me/your_channel</code> "
            "или <code>@your_channel</code>"
        )
        return

    if parsed["type"] == "private":
        await state.update_data(
            username=None,
            link=parsed["link"],
            title=None,
            is_private=True,
        )
        await state.set_state(SubsWizard.waiting_title_manual)
        await message.answer(
            "🔒 <b>Приватный канал по инвайт-ссылке</b>\n\n"
            "⚠️ Бот не сможет проверять подписки на приватный канал "
            "без публичного @username.\n\n"
            "Рекомендую использовать <b>публичный канал</b>.\n\n"
            "Введи название для этой кампании (для внутреннего использования):"
        )
        return

    username = parsed["username"]
    link = parsed["link"]

    await message.answer("🔎 Проверяю канал…")

    bot = message.bot
    info = await resolve_channel(bot, username)

    if info is None:
        await state.update_data(
            username=username,
            link=link,
            title=None,
            is_private=False,
        )
        await state.set_state(SubsWizard.waiting_title_manual)
        await message.answer(
            "⚠️ <b>Не удалось получить название автоматически</b>\n\n"
            "Возможные причины:\n"
            "• Бот не админ канала\n"
            "• Канал закрытый\n"
            "• Неверный @username\n\n"
            "Введи название канала вручную:"
        )
        return

    is_admin_in_channel = await can_check_subscription(bot, username)

    await state.update_data(
        username=username,
        link=link,
        title=info["title"],
        is_private=False,
        is_admin=is_admin_in_channel,
    )

    # Переходим к цене
    await state.set_state(SubsWizard.waiting_price)

    warn_line = "" if is_admin_in_channel else (
        "\n\n⚠️ <b>Бот не админ канала!</b>\n"
        "Проверка подписки работать не будет.\n"
        "Добавь бота в админы канала и создай кампанию заново."
    )

    await message.answer(
        f"✅ <b>Найден канал:</b>\n\n"
        f"📢 Название: <b>{info['title']}</b>\n"
        f"🆔 @{username}\n"
        f"🔗 {link}"
        f"{warn_line}\n\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"💰 <b>Шаг 2. Цена за подписчика</b>\n\n"
        f"Сколько платим за одного подписчика?\n"
        f"Пример: <code>15</code> или <code>12.5</code>",
        reply_markup=_number_kb("price"),
    )


# ============================================================
# ШАГ 2a: НАЗВАНИЕ ВРУЧНУЮ
# ============================================================
@router.message(SubsWizard.waiting_title_manual)
async def process_title_manual(message: Message, state: FSMContext):
    if not _is_admin(message.from_user.id):
        return

    title = (message.text or "").strip()
    if not title or len(title) > 128:
        await message.answer("❌ Название должно быть 1–128 символов. Попробуй ещё раз.")
        return

    data = await state.get_data()
    await state.update_data(title=title)
    await state.set_state(SubsWizard.waiting_price)

    username = data.get("username")
    link = data.get("link", "")
    is_private = data.get("is_private", False)

    if is_private:
        summary = (
            f"📢 Название: <b>{title}</b>\n"
            f"🔒 Приватный канал по ссылке"
        )
    else:
        summary = (
            f"📢 Название: <b>{title}</b>\n"
            f"🆔 @{username}\n"
            f"🔗 {link}"
        )

    await message.answer(
        f"✅ <b>Сохранено:</b>\n\n{summary}\n\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"💰 <b>Шаг 2. Цена за подписчика</b>\n\n"
        f"Сколько платим за одного подписчика?\n"
        f"Пример: <code>15</code> или <code>12.5</code>",
        reply_markup=_number_kb("price"),
    )


# ============================================================
# ШАГ 2: ЦЕНА
# ============================================================
@router.message(SubsWizard.waiting_price)
async def process_price(message: Message, state: FSMContext):
    if not _is_admin(message.from_user.id):
        return

    text = (message.text or "").strip().replace(",", ".")
    try:
        price = float(text)
    except ValueError:
        await message.answer("❌ Не похоже на число. Попробуй ещё раз.")
        return

    if price < 0 or price > 100_000:
        await message.answer("❌ Цена должна быть от 0 до 100000 ₽.")
        return

    await state.update_data(price=price)
    await state.set_state(SubsWizard.waiting_limit)

    await message.answer(
        f"✅ Цена: <b>{price:.2f} ₽</b>\n\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👥 <b>Шаг 3. Лимит подписчиков</b>\n\n"
        f"Сколько максимум подписчиков принять?\n"
        f"Отправь <code>0</code>, если без лимита.\n"
        f"Пример: <code>1000</code>",
        reply_markup=_number_kb("limit"),
    )


# ============================================================
# ШАГ 3: ЛИМИТ
# ============================================================
@router.message(SubsWizard.waiting_limit)
async def process_limit(message: Message, state: FSMContext):
    if not _is_admin(message.from_user.id):
        return

    text = (message.text or "").strip().replace(",", ".")
    try:
        limit = int(float(text))
    except ValueError:
        await message.answer("❌ Не похоже на число. Попробуй ещё раз.")
        return

    if limit < 0 or limit > 1_000_000:
        await message.answer("❌ Лимит должен быть от 0 до 1000000.")
        return

    await state.update_data(subscriber_limit=limit)
    await state.set_state(SubsWizard.waiting_budget)

    limit_str = "∞ (без лимита)" if limit == 0 else str(limit)

    await message.answer(
        f"✅ Лимит: <b>{limit_str}</b>\n\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"💵 <b>Шаг 4. Бюджет кампании</b>\n\n"
        f"Сколько всего готовы заплатить?\n"
        f"Отправь <code>0</code>, если без бюджета.\n"
        f"Пример: <code>5000</code>",
        reply_markup=_number_kb("budget"),
    )


# ============================================================
# ШАГ 4: БЮДЖЕТ
# ============================================================
@router.message(SubsWizard.waiting_budget)
async def process_budget(message: Message, state: FSMContext):
    if not _is_admin(message.from_user.id):
        return

    text = (message.text or "").strip().replace(",", ".")
    try:
        budget = float(text)
    except ValueError:
        await message.answer("❌ Не похоже на число. Попробуй ещё раз.")
        return

    if budget < 0 or budget > 10_000_000:
        await message.answer("❌ Бюджет должен быть от 0 до 10000000 ₽.")
        return

    await state.update_data(budget=budget)
    await state.set_state(SubsWizard.confirming)

    data = await state.get_data()
    await _show_confirm(message, data)


# ============================================================
# ПОДТВЕРЖДЕНИЕ
# ============================================================
async def _show_confirm(message: Message, data: dict) -> None:
    """Показывает сводку для подтверждения."""
    title = data.get("title") or "Без названия"
    username = data.get("username")
    link = data.get("link", "")
    is_private = data.get("is_private", False)
    price = data.get("price", 0.0)
    limit = data.get("subscriber_limit", 0)
    budget = data.get("budget", 0.0)

    limit_str = "∞" if limit == 0 else str(limit)
    budget_str = "∞" if budget == 0 else f"{budget:.0f} ₽"

    if is_private:
        channel_line = "🔒 Приватный канал по ссылке"
    else:
        channel_line = f"🆔 @{username}\n🔗 {link}"

    text = (
        f"✅ <b>ГОТОВО К СОЗДАНИЮ</b>\n\n"
        f"📢 Название: <b>{title}</b>\n"
        f"{channel_line}\n\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"💰 Цена за подписчика: <b>{price:.2f} ₽</b>\n"
        f"👥 Лимит подписчиков: <b>{limit_str}</b>\n"
        f"💵 Бюджет: <b>{budget_str}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"Создать кампанию?"
    )
    await message.answer(text, reply_markup=_confirm_kb())


# ============================================================
# ШАГ 5: СОЗДАНИЕ
# ============================================================
@router.callback_query(F.data == "subs_wiz_confirm")
async def cb_confirm(callback: CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return

    data = await state.get_data()
    username = data.get("username")
    link = data.get("link", "")
    title = data.get("title") or username or "Без названия"
    is_private = data.get("is_private", False)
    price = float(data.get("price", 0.0))
    limit = int(data.get("subscriber_limit", 0))
    budget = float(data.get("budget", 0.0))

    await state.clear()

    channel_id = f"@{username}" if username else None

    if not channel_id and not is_private:
        await callback.message.answer("❌ Ошибка: не удалось определить @username канала.")
        return

    async with async_session() as session:
        c = SubscriptionCampaign(
            name=title,
            status="active" if channel_id else "draft",
            is_active=bool(channel_id),
            channel_id=channel_id,
            channel_username=username,
            channel_link=link,
            price_per_subscription=price,
            subscriber_limit=limit,
            budget=budget,
            started_at=datetime.now(timezone.utc) if channel_id else None,
        )
        session.add(c)
        await session.commit()
        await session.refresh(c)

    await callback.answer("✅ Создано")

    limit_str = "∞" if limit == 0 else str(limit)
    budget_str = "∞" if budget == 0 else f"{budget:.0f} ₽"

    if channel_id:
        text = (
            f"✅ <b>Кампания #{c.id} создана и активирована</b>\n\n"
            f"📢 {title}\n"
            f"🆔 @{username}\n"
            f"🔗 {link}\n\n"
            f"💰 Цена: <b>{price:.2f} ₽</b>\n"
            f"👥 Лимит: <b>{limit_str}</b>\n"
            f"💵 Бюджет: <b>{budget_str}</b>\n\n"
            f"Теперь при включённом флаге обязательных подписок "
            f"юзеры будут видеть оффер."
        )
    else:
        text = (
            f"⚠️ <b>Кампания #{c.id} сохранена как черновик</b>\n\n"
            f"📢 {title}\n"
            f"🔗 {link}\n\n"
            f"Причина: канал приватный или @username не определён — "
            f"проверка подписки не сможет работать."
        )

    try:
        await callback.message.edit_text(text)
    except Exception:
        await callback.message.answer(text)


# ============================================================
# ОТМЕНА / РЕДАКТИРОВАНИЕ
# ============================================================
@router.callback_query(F.data == "subs_wiz_cancel")
async def cb_cancel(callback: CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return

    await state.clear()
    await callback.answer("Отменено")
    try:
        await callback.message.edit_text("❌ Создание кампании отменено.")
    except Exception:
        await callback.message.answer("❌ Создание кампании отменено.")


@router.callback_query(F.data == "subs_wiz_edit_title")
async def cb_edit_title(callback: CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return

    # Позволяем отредактировать название или цену — пока только название
    await state.set_state(SubsWizard.waiting_title_manual)
    await callback.answer()
    await callback.message.answer(
        "✏️ Введи новое название канала:",
        reply_markup=_cancel_kb(),
    )