"""
Личное сообщение одному пользователю (админ).

Доступ: /admin → 📨 Личное сообщение.

Флоу:
1. Поиск юзера: tg_id / @username / user_id / 📋 последние 20.
2. Карточка юзера → подтверждение.
3. Выбор типа контента: текст / текст+ссылка / текст+фото / PDF / PDF+подпись.
4. Ввод контента.
5. Превью → отправка.
6. Лог в events (admin_dm_sent).
"""

import asyncio
from typing import Optional

from aiogram import F, Router
from aiogram.exceptions import TelegramForbiddenError
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy import or_, select

from bot.keyboards.admin import (
    dm_cancel_kb,
    dm_content_type_kb,
    dm_preview_kb,
    dm_user_card_kb,
    dm_user_list_kb,
    dm_user_search_kb,
)
from config import config
from database.connection import async_session
from database.models import User
from services.analytics.tracker import track
from utils.logging import get_logger

router = Router()
logger = get_logger(__name__)


def _is_admin(telegram_id: int) -> bool:
    return telegram_id in config.ADMIN_IDS


# ============================================================
# FSM
# ============================================================
class DMWizard(StatesGroup):
    waiting_user = State()        # ждём tg_id / @username / user_id
    waiting_content = State()     # выбор типа контента
    waiting_text = State()        # ввод текста (для text)
    waiting_link = State()        # ввод ссылки (для text_link)
    waiting_photo = State()       # фото (для text_photo)
    waiting_caption = State()     # подпись к фото (для text_photo)
    waiting_pdf = State()         # PDF (для pdf / pdf_caption)
    waiting_pdf_caption = State() # подпись к PDF
    confirming = State()          # превью → отправка


# ============================================================
# ВХОД
# ============================================================
@router.callback_query(F.data == "adm_dm")
async def cb_dm_entry(callback: CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return

    await callback.answer()
    await state.clear()
    await state.set_state(DMWizard.waiting_user)

    await callback.message.answer(
        "📨 <b>Личное сообщение</b>\n\n"
        "Отправь одним из способов:\n"
        "• <b>tg_id</b> — <code>462035571</code>\n"
        "• <b>@username</b> — <code>@flaimes313</code>\n"
        "• <b>user_id</b> (внутренний) — например <code>42</code> (если нет @)\n\n"
        "Или жми «📋 Последние 20», чтобы выбрать из списка.",
        reply_markup=dm_user_search_kb(),
    )


# ============================================================
# СПИСОК ПОСЛЕДНИХ 20
# ============================================================
@router.callback_query(F.data == "dm_show_last")
async def cb_dm_show_last(callback: CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id):
        return

    await callback.answer()

    async with async_session() as session:
        users = (await session.execute(
            select(User).order_by(User.id.desc()).limit(20)
        )).scalars().all()

    if not users:
        await callback.message.answer(
            "Пользователей нет.",
            reply_markup=dm_cancel_kb(),
        )
        return

    lines = ["📋 <b>Последние 20 юзеров</b>\n"]
    for u in users:
        uname = f"@{u.username}" if u.username else "—"
        name = u.first_name or "—"
        lines.append(f"• <b>#{u.id}</b> · {name} · {uname} · <code>{u.telegram_id}</code>")

    try:
        await callback.message.edit_text(
            "\n".join(lines),
            reply_markup=dm_user_list_kb(users),
        )
    except Exception:
        await callback.message.answer(
            "\n".join(lines),
            reply_markup=dm_user_list_kb(users),
        )


@router.callback_query(F.data.startswith("dm_pick_"))
async def cb_dm_pick_user(callback: CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id):
        return

    await callback.answer()

    try:
        user_id = int(callback.data.replace("dm_pick_", ""))
    except ValueError:
        await callback.message.answer("Некорректный ID.")
        return

    async with async_session() as session:
        user = (await session.execute(
            select(User).where(User.id == user_id)
        )).scalar_one_or_none()

    if user is None:
        await callback.message.answer("Юзер не найден.")
        return

    await _show_user_card(callback.message, state, user)


# ============================================================
# ПОИСК ПО ВВОДУ
# ============================================================
@router.message(DMWizard.waiting_user, F.text)
async def on_user_input(message: Message, state: FSMContext):
    if not _is_admin(message.from_user.id):
        return

    raw = (message.text or "").strip()
    if not raw or raw.startswith("/"):
        return

    user: Optional[User] = None

    # @username
    if raw.startswith("@"):
        uname = raw[1:].lower()
        async with async_session() as session:
            user = (await session.execute(
                select(User).where(User.username.ilike(uname))
            )).scalar_one_or_none()

    # tg_id (большие числа — 6+ цифр)
    elif raw.isdigit() and len(raw) >= 6:
        async with async_session() as session:
            user = (await session.execute(
                select(User).where(User.telegram_id == int(raw))
            )).scalar_one_or_none()

    # user_id (внутренний, обычно до 100000)
    elif raw.isdigit():
        async with async_session() as session:
            user = (await session.execute(
                select(User).where(User.id == int(raw))
            )).scalar_one_or_none()

    if user is None:
        await message.answer(
            "❌ Юзер не найден. Попробуй ещё раз или жми «📋 Последние 20».",
            reply_markup=dm_user_search_kb(),
        )
        return

    await _show_user_card(message, state, user)


# ============================================================
# КАРТОЧКА ЮЗЕРА
# ============================================================
async def _show_user_card(message: Message, state: FSMContext, user: User) -> None:
    await state.update_data(
        target_user_id=user.id,
        target_telegram_id=user.telegram_id,
        target_name=user.first_name or "Игрок",
        target_username=user.username,
    )

    pro_str = "—"
    if user.premium_until:
        pro_str = user.premium_until.strftime("%d.%m.%Y")

    uname = f"@{user.username}" if user.username else "—"

    text = (
        "👤 <b>Карточка юзера</b>\n\n"
        f"<b>{user.first_name or '—'}</b> ({uname})\n"
        f"🆔 tg_id: <code>{user.telegram_id}</code>\n"
        f"🔢 user_id: <code>{user.id}</code>\n"
        f"💎 PRO до: <b>{pro_str}</b>\n"
        f"🚫 Заблокирован: {'да' if user.is_blocked else 'нет'}\n\n"
        "Пишем этому юзеру?"
    )

    kb = dm_user_card_kb(user.id)

    try:
        await message.answer(text, reply_markup=kb)
    except Exception:
        await message.answer(text, reply_markup=kb)

    # Переходим в выбор контента
    await state.set_state(DMWizard.waiting_content)
    await message.answer(
        "📨 <b>Что отправить?</b>",
        reply_markup=dm_content_type_kb(),
    )


# ============================================================
# ВЫБОР ТИПА КОНТЕНТА
# ============================================================
@router.callback_query(F.data == "dm_type_text")
async def cb_dm_type_text(callback: CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id):
        return
    await callback.answer()
    await state.update_data(dm_type="text")
    await state.set_state(DMWizard.waiting_text)
    await callback.message.answer(
        "✍️ Отправь <b>текст сообщения</b>.",
        reply_markup=dm_cancel_kb(),
    )


@router.callback_query(F.data == "dm_type_text_link")
async def cb_dm_type_text_link(callback: CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id):
        return
    await callback.answer()
    await state.update_data(dm_type="text_link")
    await state.set_state(DMWizard.waiting_text)
    await callback.message.answer(
        "✍️ Отправь <b>текст сообщения</b> (юзер увидит его вместе с кнопкой).",
        reply_markup=dm_cancel_kb(),
    )


@router.callback_query(F.data == "dm_type_text_photo")
async def cb_dm_type_text_photo(callback: CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id):
        return
    await callback.answer()
    await state.update_data(dm_type="text_photo")
    await state.set_state(DMWizard.waiting_text)
    await callback.message.answer(
        "✍️ Отправь <b>текст сообщения</b> (он пойдёт подписью к фото).",
        reply_markup=dm_cancel_kb(),
    )


@router.callback_query(F.data == "dm_type_pdf")
async def cb_dm_type_pdf(callback: CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id):
        return
    await callback.answer()
    await state.update_data(dm_type="pdf")
    await state.set_state(DMWizard.waiting_pdf)
    await callback.message.answer(
        "📄 Отправь <b>PDF-файл</b> (документом, без подписи).",
        reply_markup=dm_cancel_kb(),
    )


@router.callback_query(F.data == "dm_type_pdf_caption")
async def cb_dm_type_pdf_caption(callback: CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id):
        return
    await callback.answer()
    await state.update_data(dm_type="pdf_caption")
    await state.set_state(DMWizard.waiting_pdf)
    await callback.message.answer(
        "📄 Отправь <b>PDF-файл</b> (сначала файл, потом подпись).",
        reply_markup=dm_cancel_kb(),
    )


# ============================================================
# ВВОД ТЕКСТА
# ============================================================
@router.message(DMWizard.waiting_text, F.text)
async def on_dm_text(message: Message, state: FSMContext):
    if not _is_admin(message.from_user.id):
        return

    text = (message.text or "").strip()
    if not text:
        await message.answer("❌ Пустой текст. Отправь снова.")
        return

    data = await state.get_data()
    dm_type = data.get("dm_type")

    await state.update_data(dm_text=text)

    if dm_type == "text":
        await state.set_state(DMWizard.confirming)
        await _show_preview(message, state)

    elif dm_type == "text_link":
        await state.set_state(DMWizard.waiting_link)
        await message.answer(
            "🔗 Отправь <b>ссылку на чек</b>.\n\n"
            "Например: <code>https://lknpd.nalog.ru/...</code>",
            reply_markup=dm_cancel_kb(),
        )

    elif dm_type == "text_photo":
        await state.set_state(DMWizard.waiting_photo)
        await message.answer(
            "🖼 Отправь <b>фото чека</b>.",
            reply_markup=dm_cancel_kb(),
        )


# ============================================================
# ВВОД ССЫЛКИ
# ============================================================
@router.message(DMWizard.waiting_link, F.text)
async def on_dm_link(message: Message, state: FSMContext):
    if not _is_admin(message.from_user.id):
        return

    link = (message.text or "").strip()
    if not (link.startswith("http://") or link.startswith("https://")):
        await message.answer(
            "❌ Ссылка должна начинаться с <code>http://</code> или <code>https://</code>."
        )
        return

    await state.update_data(dm_link=link)
    await state.set_state(DMWizard.confirming)
    await _show_preview(message, state)


# ============================================================
# ФОТО (для text_photo)
# ============================================================
@router.message(DMWizard.waiting_photo, F.photo)
async def on_dm_photo(message: Message, state: FSMContext):
    if not _is_admin(message.from_user.id):
        return

    photo = message.photo[-1]
    await state.update_data(dm_photo_file_id=photo.file_id)
    await state.set_state(DMWizard.confirming)
    await _show_preview(message, state)


@router.message(DMWizard.waiting_photo)
async def on_dm_photo_invalid(message: Message):
    if not _is_admin(message.from_user.id):
        return
    await message.answer("❌ Нужно отправить <b>фото</b>.")


# ============================================================
# PDF (для pdf / pdf_caption)
# ============================================================
@router.message(DMWizard.waiting_pdf, F.document)
async def on_dm_pdf(message: Message, state: FSMContext):
    if not _is_admin(message.from_user.id):
        return

    doc = message.document
    if not doc:
        await message.answer("❌ Не удалось получить файл.")
        return

    mime = doc.mime_type or ""
    name = (doc.file_name or "").lower()
    if "pdf" not in mime and not name.endswith(".pdf"):
        await message.answer("❌ Нужен именно PDF-файл.")
        return

    await state.update_data(dm_pdf_file_id=doc.file_id, dm_pdf_name=doc.file_name)

    data = await state.get_data()
    dm_type = data.get("dm_type")

    if dm_type == "pdf":
        await state.set_state(DMWizard.confirming)
        await _show_preview(message, state)
    else:
        await state.set_state(DMWizard.waiting_pdf_caption)
        await message.answer(
            "✍️ Отправь <b>подпись</b> к PDF (короткий текст).",
            reply_markup=dm_cancel_kb(),
        )


@router.message(DMWizard.waiting_pdf)
async def on_dm_pdf_invalid(message: Message):
    if not _is_admin(message.from_user.id):
        return
    await message.answer("❌ Нужно отправить <b>PDF-файл</b> (документом).")


@router.message(DMWizard.waiting_pdf_caption, F.text)
async def on_dm_pdf_caption(message: Message, state: FSMContext):
    if not _is_admin(message.from_user.id):
        return

    caption = (message.text or "").strip()
    if not caption:
        await message.answer("❌ Пустая подпись.")
        return
    if len(caption) > 1024:
        await message.answer(f"⚠️ Подпись > 1024 ({len(caption)}). Сократи.")
        return

    await state.update_data(dm_caption=caption)
    await state.set_state(DMWizard.confirming)
    await _show_preview(message, state)


# ============================================================
# ПРЕВЬЮ
# ============================================================
async def _show_preview(message: Message, state: FSMContext):
    data = await state.get_data()
    dm_type = data.get("dm_type")
    dm_text = data.get("dm_text")
    dm_link = data.get("dm_link")
    dm_photo_file_id = data.get("dm_photo_file_id")
    dm_pdf_file_id = data.get("dm_pdf_file_id")
    dm_pdf_name = data.get("dm_pdf_name")
    dm_caption = data.get("dm_caption")
    target_username = data.get("target_username")
    target_name = data.get("target_name")

    header = (
        f"📨 <b>Предпросмотр</b>\n\n"
        f"👤 Кому: <b>{target_name}</b>"
        + (f" (@{target_username})" if target_username else "")
        + "\n\n"
    )

    if dm_type == "text":
        await message.answer(
            f"{header}───────────────────\n{dm_text}\n───────────────────\n\n"
            "Отправить?",
            reply_markup=dm_preview_kb(),
        )
    elif dm_type == "text_link":
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="📄 Открыть чек", url=dm_link)],
            ]
        )
        await message.answer(
            f"{header}───────────────────\n{dm_text}\n───────────────────\n\n"
            f"🔗 Кнопка: 📄 Открыть чек → {dm_link}\n\n"
            "Отправить?",
            reply_markup=kb,
        )
        await message.answer(
            "Нажми «🚀 Отправить» или «❌ Отмена»:",
            reply_markup=dm_preview_kb(),
        )
    elif dm_type == "text_photo":
        await message.answer_photo(
            dm_photo_file_id,
            caption=f"{header}{dm_text}\n\nОтправить?",
        )
        await message.answer(
            "Нажми «🚀 Отправить» или «❌ Отмена»:",
            reply_markup=dm_preview_kb(),
        )
    elif dm_type == "pdf":
        await message.answer_document(
            dm_pdf_file_id,
            caption=f"{header}<i>{dm_pdf_name or 'чек.pdf'}</i>\n\nОтправить?",
        )
        await message.answer(
            "Нажми «🚀 Отправить» или «❌ Отмена»:",
            reply_markup=dm_preview_kb(),
        )
    elif dm_type == "pdf_caption":
        await message.answer_document(
            dm_pdf_file_id,
            caption=f"{header}{dm_caption or ''}\n\nОтправить?",
        )
        await message.answer(
            "Нажми «🚀 Отправить» или «❌ Отмена»:",
            reply_markup=dm_preview_kb(),
        )


# ============================================================
# ОТПРАВКА
# ============================================================
@router.callback_query(F.data == "dm_confirm")
async def cb_dm_confirm(callback: CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id):
        return

    await callback.answer("Отправляю…")

    data = await state.get_data()
    dm_type = data.get("dm_type")
    dm_text = data.get("dm_text")
    dm_link = data.get("dm_link")
    dm_photo_file_id = data.get("dm_photo_file_id")
    dm_pdf_file_id = data.get("dm_pdf_file_id")
    dm_caption = data.get("dm_caption")
    target_telegram_id = data.get("target_telegram_id")
    target_user_id = data.get("target_user_id")
    target_name = data.get("target_name")
    target_username = data.get("target_username")

    await state.clear()

    if not target_telegram_id:
        await callback.message.answer("❌ Потерян получатель. Начни заново.")
        return

    # Клавиатура для text_link
    kb = None
    if dm_type == "text_link" and dm_link:
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="📄 Открыть чек", url=dm_link)],
            ]
        )

    sent_ok = False
    error_reason = ""

    try:
        if dm_type == "text":
            await callback.bot.send_message(
                target_telegram_id, dm_text, reply_markup=None
            )
        elif dm_type == "text_link":
            await callback.bot.send_message(
                target_telegram_id, dm_text, reply_markup=kb
            )
        elif dm_type == "text_photo":
            await callback.bot.send_photo(
                target_telegram_id, dm_photo_file_id, caption=dm_text
            )
        elif dm_type == "pdf":
            await callback.bot.send_document(
                target_telegram_id, dm_pdf_file_id
            )
        elif dm_type == "pdf_caption":
            await callback.bot.send_document(
                target_telegram_id, dm_pdf_file_id, caption=dm_caption or ""
            )
        else:
            error_reason = "unknown_type"
            raise ValueError(f"Unknown dm_type: {dm_type}")

        sent_ok = True
    except TelegramForbiddenError:
        error_reason = "blocked"
        logger.warning(f"[DM] user blocked bot: tg={target_telegram_id}")
        async with async_session() as session:
            u = (await session.execute(
                select(User).where(User.telegram_id == target_telegram_id)
            )).scalar_one_or_none()
            if u and not u.is_blocked:
                u.is_blocked = True
                await session.commit()
    except Exception as e:
        error_reason = "failed"
        logger.exception(f"[DM] send failed tg={target_telegram_id}")

    if sent_ok:
        try:
            await track(
                "admin_dm_sent",
                telegram_id=target_telegram_id,
                user_id=target_user_id,
                payload={
                    "admin_id": callback.from_user.id,
                    "dm_type": dm_type,
                    "sent_ok": True,
                },
            )
        except Exception:
            logger.exception("[DM] track failed")

        await callback.message.answer(
            f"✅ <b>Отправлено</b>\n\n"
            f"👤 {target_name}"
            + (f" (@{target_username})" if target_username else "")
            + f"\nТип: {dm_type}"
        )
    else:
        try:
            await track(
                "admin_dm_sent",
                telegram_id=target_telegram_id,
                user_id=target_user_id,
                payload={
                    "admin_id": callback.from_user.id,
                    "dm_type": dm_type,
                    "sent_ok": False,
                    "reason": error_reason,
                },
            )
        except Exception:
            pass

        if error_reason == "blocked":
            await callback.message.answer(
                "🚫 <b>Не удалось отправить</b>\n\n"
                "Пользователь заблокировал бота. "
                "Он помечен как «заблокирован»."
            )
        else:
            await callback.message.answer(
                "❌ <b>Ошибка отправки.</b> Попробуй позже."
            )


# ============================================================
# ОТМЕНА
# ============================================================
@router.callback_query(F.data == "dm_cancel")
async def cb_dm_cancel(callback: CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id):
        return

    await state.clear()
    await callback.answer("Отменено")

    try:
        await callback.message.edit_text("❌ Отменено.")
    except Exception:
        await callback.message.answer("❌ Отменено.")


@router.callback_query(F.data == "dm_back_to_user")
async def cb_dm_back_to_user(callback: CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id):
        return

    await callback.answer()
    await state.set_state(DMWizard.waiting_user)
    await callback.message.answer(
        "📨 Отправь tg_id, @username или жми «📋 Последние 20».",
        reply_markup=dm_user_search_kb(),
    )