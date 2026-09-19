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
from sqlalchemy import select

from bot.keyboards.admin import (
    broadcast_add_button_kb,
    broadcast_cancel_kb,
    broadcast_confirm_kb,
    broadcast_menu_kb,
)
from config import config
from database.connection import async_session
from database.models import User
from utils.logging import get_logger

router = Router()
logger = get_logger(__name__)


def _is_admin(telegram_id: int) -> bool:
    return telegram_id in config.ADMIN_IDS


# ============================================================
# FSM
# ============================================================
class BroadcastWizard(StatesGroup):
    choosing_type = State()
    waiting_text = State()
    waiting_photo = State()
    waiting_caption = State()
    waiting_button = State()
    confirming = State()


# ============================================================
# ТОЧКА ВХОДА
# ============================================================
@router.callback_query(F.data == "adm_broadcast")
async def cb_broadcast_menu(callback: CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return

    await callback.answer()
    await state.clear()

    await callback.message.answer(
        "📨 <b>Рассылка</b>\n\n"
        "Выбери тип контента:\n"
        "• ✍️ Только текст\n"
        "• 🖼 Только картинка\n"
        "• 🖼+✍️ Картинка + текст",
        reply_markup=broadcast_menu_kb(),
    )


# ============================================================
# ВЫБОР ТИПА
# ============================================================
@router.callback_query(F.data == "bc_type_text")
async def cb_type_text(callback: CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id):
        return
    await callback.answer()
    await state.update_data(bc_type="text")
    await state.set_state(BroadcastWizard.waiting_text)
    await callback.message.answer(
        "✍️ Отправь <b>текст рассылки</b> (HTML-разметка поддерживается).\n\n"
        "Ссылку в тексте можно оформить так:\n"
        "<code>&lt;a href=\"https://t.me/channel\"&gt;Подпишись&lt;/a&gt;</code>",
        reply_markup=broadcast_cancel_kb(),
    )


@router.callback_query(F.data == "bc_type_photo")
async def cb_type_photo(callback: CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id):
        return
    await callback.answer()
    await state.update_data(bc_type="photo")
    await state.set_state(BroadcastWizard.waiting_photo)
    await callback.message.answer(
        "🖼 Отправь <b>картинку</b> (фото, без подписи).",
        reply_markup=broadcast_cancel_kb(),
    )


@router.callback_query(F.data == "bc_type_photo_text")
async def cb_type_photo_text(callback: CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id):
        return
    await callback.answer()
    await state.update_data(bc_type="photo_text")
    await state.set_state(BroadcastWizard.waiting_photo)
    await callback.message.answer(
        "🖼 Отправь <b>картинку</b> (фото).",
        reply_markup=broadcast_cancel_kb(),
    )


# ============================================================
# ТЕКСТ
# ============================================================
@router.message(BroadcastWizard.waiting_text)
async def on_text(message: Message, state: FSMContext):
    if not _is_admin(message.from_user.id):
        return
    text = (message.text or "").strip()
    if not text:
        await message.answer("❌ Пустое сообщение. Отправь текст.")
        return

    await state.update_data(bc_text=text)
    # Переходим к опции «добавить кнопку»
    await state.set_state(BroadcastWizard.waiting_button)
    await message.answer(
        "🔗 <b>Добавить кнопку со ссылкой?</b>\n\n"
        "Можно добавить одну inline-кнопку с URL, "
        "которая появится под сообщением.",
        reply_markup=broadcast_add_button_kb(),
    )


# ============================================================
# ФОТО
# ============================================================
@router.message(BroadcastWizard.waiting_photo, F.photo)
async def on_photo(message: Message, state: FSMContext):
    if not _is_admin(message.from_user.id):
        return
    photo = message.photo[-1]
    data = await state.get_data()
    bc_type = data.get("bc_type")
    await state.update_data(bc_file_id=photo.file_id)

    if bc_type == "photo":
        # Только картинка — сразу к вопросу про кнопку
        await state.set_state(BroadcastWizard.waiting_button)
        await message.answer(
            "🔗 <b>Добавить кнопку со ссылкой?</b>",
            reply_markup=broadcast_add_button_kb(),
        )
    else:
        await state.set_state(BroadcastWizard.waiting_caption)
        await message.answer(
            "✍️ Отправь <b>текст</b> под картинкой (caption).",
            reply_markup=broadcast_cancel_kb(),
        )


@router.message(BroadcastWizard.waiting_photo)
async def on_photo_invalid(message: Message):
    if not _is_admin(message.from_user.id):
        return
    await message.answer("❌ Нужно отправить именно <b>фото</b>.")


# ============================================================
# CAPTION
# ============================================================
@router.message(BroadcastWizard.waiting_caption)
async def on_caption(message: Message, state: FSMContext):
    if not _is_admin(message.from_user.id):
        return
    caption = (message.text or "").strip()
    if not caption:
        await message.answer("❌ Пустой текст. Отправь caption.")
        return
    if len(caption) > 1024:
        await message.answer(
            f"⚠️ Текст слишком длинный ({len(caption)} символов). "
            f"Максимум 1024 для caption. Сократи."
        )
        return

    await state.update_data(bc_caption=caption)
    await state.set_state(BroadcastWizard.waiting_button)
    await message.answer(
        "🔗 <b>Добавить кнопку со ссылкой?</b>",
        reply_markup=broadcast_add_button_kb(),
    )


# ============================================================
# ВЫБОР: ДОБАВИТЬ КНОПКУ ИЛИ НЕТ
# ============================================================
@router.callback_query(F.data == "bc_add_button")
async def cb_add_button(callback: CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id):
        return
    await callback.answer()
    await state.set_state(BroadcastWizard.waiting_button)
    await callback.message.answer(
        "🔗 Отправь данные для кнопки в формате:\n\n"
        "<code>Текст кнопки | https://ссылка</code>\n\n"
        "Например:\n"
        "<code>📢 Подписаться на канал | https://t.me/my_channel</code>\n"
        "<code>🌐 Открыть сайт | https://example.com</code>",
        reply_markup=broadcast_cancel_kb(),
    )


@router.message(BroadcastWizard.waiting_button)
async def on_button_data(message: Message, state: FSMContext):
    if not _is_admin(message.from_user.id):
        return
    text = (message.text or "").strip()

    if "|" not in text:
        await message.answer(
            "❌ Нужен формат: <code>Текст кнопки | URL</code>"
        )
        return

    parts = text.split("|", 1)
    label = parts[0].strip()
    url = parts[1].strip()

    if not label or not url:
        await message.answer("❌ Пустой текст кнопки или ссылка.")
        return

    if not (url.startswith("http://") or url.startswith("https://") or url.startswith("tg://")):
        await message.answer(
            "❌ Ссылка должна начинаться с <code>http://</code>, "
            "<code>https://</code> или <code>tg://</code>."
        )
        return

    if len(label) > 64:
        await message.answer("❌ Текст кнопки не должен превышать 64 символа.")
        return

    await state.update_data(bc_button_label=label, bc_button_url=url)
    await state.set_state(BroadcastWizard.confirming)
    await _show_preview(message, state)


@router.callback_query(F.data == "bc_no_button")
async def cb_no_button(callback: CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id):
        return
    await callback.answer()
    await state.set_state(BroadcastWizard.confirming)
    await _show_preview(callback.message, state)


# ============================================================
# ПРЕВЬЮ
# ============================================================
async def _show_preview(message: Message, state: FSMContext):
    data = await state.get_data()
    bc_type = data.get("bc_type")
    bc_text = data.get("bc_text")
    bc_file_id = data.get("bc_file_id")
    bc_caption = data.get("bc_caption")
    bc_button_label = data.get("bc_button_label")
    bc_button_url = data.get("bc_button_url")

    # Клавиатура с URL, если задана
    kb: Optional[InlineKeyboardMarkup] = None
    if bc_button_label and bc_button_url:
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=bc_button_label, url=bc_button_url)],
            ]
        )

    # Считаем получателей
    try:
        async with async_session() as session:
            total_count = len((await session.execute(
                select(User).where(User.is_blocked.is_(False))
            )).scalars().all())
    except Exception:
        logger.exception("Failed to count users")
        total_count = 0

    header = (
        f"📨 <b>Предпросмотр рассылки</b>\n\n"
        f"👥 Получателей: <b>{total_count}</b>\n"
    )
    if bc_button_label:
        header += f"🔗 Кнопка: <b>{bc_button_label}</b> → {bc_button_url}\n"
    header += "\n"

    if bc_type == "text":
        await message.answer(
            f"{header}───────────────────\n{bc_text}\n───────────────────\n\n"
            f"Отправить?",
            reply_markup=kb or broadcast_confirm_kb(),
        )
        # Отдельно подтверждающая клавиатура
        if kb is not None:
            await message.answer(
                "Нажми «🚀 Отправить всем» или «❌ Отмена»:",
                reply_markup=broadcast_confirm_kb(),
            )
    elif bc_type == "photo":
        await message.answer_photo(
            bc_file_id,
            caption=f"{header}Только картинка (без текста).\n\nОтправить?",
            reply_markup=kb or broadcast_confirm_kb(),
        )
        if kb is not None:
            await message.answer(
                "Нажми «🚀 Отправить всем» или «❌ Отмена»:",
                reply_markup=broadcast_confirm_kb(),
            )
    elif bc_type == "photo_text":
        await message.answer_photo(
            bc_file_id,
            caption=bc_caption,
            reply_markup=kb,
        )
        await message.answer(
            f"{header}Отправить эту рассылку?",
            reply_markup=broadcast_confirm_kb(),
        )


# ============================================================
# ПОДТВЕРЖДЕНИЕ → РАССЫЛКА
# ============================================================
@router.callback_query(F.data == "bc_confirm")
async def cb_confirm(callback: CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id):
        return
    await callback.answer("Начинаю рассылку…")

    data = await state.get_data()
    bc_type = data.get("bc_type")
    bc_text = data.get("bc_text")
    bc_file_id = data.get("bc_file_id")
    bc_caption = data.get("bc_caption")
    bc_button_label = data.get("bc_button_label")
    bc_button_url = data.get("bc_button_url")

    await state.clear()

    # Клавиатура с URL
    kb: Optional[InlineKeyboardMarkup] = None
    if bc_button_label and bc_button_url:
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=bc_button_label, url=bc_button_url)],
            ]
        )

    # Получатели
    async with async_session() as session:
        users = (await session.execute(
            select(User).where(User.is_blocked.is_(False))
        )).scalars().all()

    total = len(users)
    await callback.message.answer(
        f"🚀 <b>Рассылка запущена</b>\n\n"
        f"👥 Получателей: {total}\n\n"
        f"Это может занять несколько минут…"
    )

    sent = 0
    failed = 0

    for i, user in enumerate(users, 1):
        try:
            if bc_type == "text":
                await callback.bot.send_message(
                    user.telegram_id, bc_text, reply_markup=kb
                )
            elif bc_type == "photo":
                await callback.bot.send_photo(
                    user.telegram_id, bc_file_id, reply_markup=kb
                )
            elif bc_type == "photo_text":
                await callback.bot.send_photo(
                    user.telegram_id, bc_file_id, caption=bc_caption, reply_markup=kb
                )
            sent += 1
        except TelegramForbiddenError:
            async with async_session() as session:
                u = (await session.execute(
                    select(User).where(User.id == user.id)
                )).scalar_one_or_none()
                if u:
                    u.is_blocked = True
                    await session.commit()
            failed += 1
        except Exception as e:
            logger.warning(f"Broadcast failed for {user.telegram_id}: {e}")
            failed += 1

        await asyncio.sleep(0.05)

        if i % 100 == 0:
            try:
                await callback.message.answer(
                    f"📊 Прогресс: {i}/{total} (отправлено: {sent}, ошибок: {failed})"
                )
            except Exception:
                pass

    await callback.message.answer(
        f"✅ <b>Рассылка завершена</b>\n\n"
        f"👥 Получателей: {total}\n"
        f"✅ Доставлено: <b>{sent}</b>\n"
        f"❌ Ошибок: <b>{failed}</b>"
    )


# ============================================================
# ОТМЕНА
# ============================================================
@router.callback_query(F.data == "bc_cancel")
async def cb_cancel(callback: CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id):
        return
    await state.clear()
    await callback.answer("Отменено")
    try:
        await callback.message.edit_text("❌ Рассылка отменена.")
    except Exception:
        await callback.message.answer("❌ Рассылка отменена.")