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
    confirming = State()


# ============================================================
# Клавиатуры
# ============================================================
def _start_kb() -> InlineKeyboardMarkup:
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
        reply_markup=_start_kb(),
    )


# ============================================================
# ШАГ 1
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
    await state.set_state(SubsWizard.confirming)

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
        f"Создать кампанию?",
        reply_markup=_confirm_kb(),
    )


# ============================================================
# ШАГ 2a: название вручную
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
    await state.set_state(SubsWizard.confirming)

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
        f"✅ <b>Готово к созданию:</b>\n\n"
        f"{summary}\n\n"
        f"Создать кампанию?",
        reply_markup=_confirm_kb(),
    )


# ============================================================
# ШАГ 3: создание
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
            price_per_subscription=2.0,
            subscriber_limit=1000,
            budget=2000,
            started_at=datetime.now(timezone.utc) if channel_id else None,
        )
        session.add(c)
        await session.commit()
        await session.refresh(c)

    await callback.answer("✅ Создано")

    if channel_id:
        text = (
            f"✅ <b>Кампания #{c.id} создана и активирована</b>\n\n"
            f"📢 {title}\n"
            f"🆔 @{username}\n"
            f"🔗 {link}\n\n"
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
# Отмена / редактирование
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

    await state.set_state(SubsWizard.waiting_title_manual)
    await callback.answer()
    await callback.message.answer("✏️ Введи новое название канала:")