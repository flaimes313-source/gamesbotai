from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select

from config import config
from database.connection import async_session
from database.models import SupportTicket, User
from utils.logging import get_logger

router = Router()
logger = get_logger(__name__)

PENDING_TICKET: dict[int, bool] = {}

# Админ, ожидающий ввода ответа: telegram_id админа → ticket_id
PENDING_ADMIN_REPLY: dict[int, int] = {}


# ============================================================
# Фильтр: срабатываем ТОЛЬКО если пользователь ждёт отправки тикета
# ============================================================
def _is_waiting_ticket(message: Message) -> bool:
    return PENDING_TICKET.get(message.from_user.id, False)


def _is_admin_waiting_reply(message: Message) -> bool:
    return message.from_user.id in PENDING_ADMIN_REPLY


def _is_admin(telegram_id: int) -> bool:
    return telegram_id in config.ADMIN_IDS


# ============================================================
# Клавиатуры
# ============================================================
def support_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✍️ Написать в поддержку", callback_data="support_write")],
            [InlineKeyboardButton(text="📖 FAQ", callback_data="support_faq")],
            [InlineKeyboardButton(text="🏠 В главное меню", callback_data="back_to_main")],
        ]
    )


def faq_back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="support_menu")],
        ]
    )


def admin_reply_kb(ticket_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="💬 Ответить",
                callback_data=f"adm_reply_{ticket_id}",
            )],
            [InlineKeyboardButton(
                text="✅ Закрыть без ответа",
                callback_data=f"adm_close_{ticket_id}",
            )],
        ]
    )


def admin_cancel_kb(ticket_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="❌ Отменить",
                callback_data=f"adm_cancel_{ticket_id}",
            )],
        ]
    )


# ============================================================
# REPLY-КНОПКА «🆘 Поддержка»
# ============================================================
@router.message(F.text == "🆘 Поддержка")
async def support_from_menu(message: Message):
    await message.answer(
        "🆘 <b>Поддержка</b>\n\n"
        "Выбери действие:",
        reply_markup=support_menu_kb(),
    )


# ============================================================
# CALLBACK-И ПОЛЬЗОВАТЕЛЯ
# ============================================================
@router.callback_query(F.data == "support_menu")
async def cb_support_menu(callback: CallbackQuery):
    await callback.answer()
    text = "🆘 <b>Поддержка</b>\n\nВыбери действие:"
    try:
        await callback.message.edit_text(text, reply_markup=support_menu_kb())
    except Exception:
        await callback.message.answer(text, reply_markup=support_menu_kb())


@router.callback_query(F.data == "support_write")
async def cb_support_write(callback: CallbackQuery):
    await callback.answer()
    PENDING_TICKET[callback.from_user.id] = True
    await callback.message.answer(
        "✍️ Напиши свой вопрос одним сообщением — мы ответим в этом чате.\n\n"
        "Чтобы отменить — /cancel"
    )


@router.callback_query(F.data == "support_faq")
async def cb_support_faq(callback: CallbackQuery):
    await callback.answer()
    text = (
        "📖 <b>FAQ</b>\n\n"
        "<b>Как работает бот?</b>\n"
        "Отправь фото — AI сделает смешной игровой профиль.\n\n"
        "<b>Это правда анализ личности?</b>\n"
        "Нет. Это развлекательная интерпретация вайба фото.\n\n"
        "<b>Как найти других игроков?</b>\n"
        "«🎯 Найти игроков» → выбери режим поиска.\n\n"
        "<b>Как выйти из игры?</b>\n"
        "«🎮 Социальная игра» → «Выйти из игры».\n\n"
        "<b>Как удалить свои данные?</b>\n"
        "Напиши в поддержку — удалим."
    )
    try:
        await callback.message.edit_text(text, reply_markup=faq_back_kb())
    except Exception:
        await callback.message.answer(text, reply_markup=faq_back_kb())


@router.message(F.text == "/cancel")
async def cmd_cancel(message: Message):
    # отмена тикета пользователем
    if PENDING_TICKET.pop(message.from_user.id, False):
        await message.answer("❌ Отменено. Тикет не создан.")
        return

    # отмена ответа админом
    if PENDING_ADMIN_REPLY.pop(message.from_user.id, None) is not None:
        await message.answer("❌ Отменено. Ответ не отправлен.")
        return

    await message.answer("Нечего отменять.")


# ============================================================
# ПОЛЬЗОВАТЕЛЬ ОТПРАВИЛ ВОПРОС
# ============================================================
@router.message(F.text & ~F.text.startswith("/"), _is_waiting_ticket)
async def handle_support_message(message: Message):
    if not PENDING_TICKET.get(message.from_user.id):
        return

    PENDING_TICKET.pop(message.from_user.id, None)

    # Сохраняем тикет
    async with async_session() as session:
        user = (await session.execute(
            select(User).where(User.telegram_id == message.from_user.id)
        )).scalar_one_or_none()

        if user is None:
            user = User(
                telegram_id=message.from_user.id,
                username=message.from_user.username,
                first_name=message.from_user.first_name,
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)

        ticket = SupportTicket(
            user_id=user.id,
            message=message.text[:2000],
            status="open",
        )
        session.add(ticket)
        await session.commit()
        await session.refresh(ticket)

    # Подтверждение пользователю
    await message.answer(
        f"✅ <b>Вопрос отправлен.</b>\n\n"
        f"Мы ответим прямо в этом чате."
    )

    # Уведомляем админов с кнопкой «Ответить»
    username_str = f"@{message.from_user.username}" if message.from_user.username else "—"
    admin_text = (
        f"🆘 <b>Вопрос #{ticket.id}</b>\n\n"
        f"👤 От: <b>{message.from_user.first_name or 'Пользователь'}</b> ({username_str})\n"
        f"🆔 <code>{message.from_user.id}</code>\n\n"
        f"💬 <b>Текст:</b>\n{message.text[:1500]}"
    )

    for admin_id in config.ADMIN_IDS:
        try:
            await message.bot.send_message(
                admin_id,
                admin_text,
                reply_markup=admin_reply_kb(ticket.id),
            )
        except Exception:
            logger.exception(f"Failed to notify admin {admin_id}")


# ============================================================
# АДМИН: НАЖАЛ «ОТВЕТИТЬ»
# ============================================================
@router.callback_query(F.data.startswith("adm_reply_"))
async def cb_admin_reply(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return

    await callback.answer()
    ticket_id = int(callback.data.replace("adm_reply_", ""))

    async with async_session() as session:
        ticket = (await session.execute(
            select(SupportTicket).where(SupportTicket.id == ticket_id)
        )).scalar_one_or_none()

    if ticket is None:
        await callback.message.answer("Тикет не найден.")
        return

    if ticket.status == "closed":
        await callback.message.answer("Тикет уже закрыт.")
        return

    PENDING_ADMIN_REPLY[callback.from_user.id] = ticket_id

    await callback.message.answer(
        f"✍️ <b>Ответ на тикет #{ticket_id}</b>\n\n"
        f"Напиши текст ответа одним сообщением — он уйдёт пользователю.\n\n"
        f"Чтобы отменить — /cancel",
        reply_markup=admin_cancel_kb(ticket_id),
    )


@router.callback_query(F.data.startswith("adm_cancel_"))
async def cb_admin_cancel(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return

    await callback.answer("Отменено")
    PENDING_ADMIN_REPLY.pop(callback.from_user.id, None)
    try:
        await callback.message.delete()
    except Exception:
        pass


@router.callback_query(F.data.startswith("adm_close_"))
async def cb_admin_close(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return

    await callback.answer("Закрыто")
    ticket_id = int(callback.data.replace("adm_close_", ""))

    async with async_session() as session:
        ticket = (await session.execute(
            select(SupportTicket).where(SupportTicket.id == ticket_id)
        )).scalar_one_or_none()

        if ticket is None:
            await callback.message.answer("Тикет не найден.")
            return

        ticket.status = "closed"
        ticket.admin_reply = None
        ticket.admin_id = callback.from_user.id
        from datetime import datetime
        ticket.closed_at = datetime.utcnow()
        await session.commit()

    # Убираем кнопку у админа, добавляем пометку
    try:
        await callback.message.edit_text(
            f"{callback.message.text}\n\n"
            f"✅ <b>Закрыто без ответа</b>",
            reply_markup=None,
        )
    except Exception:
        pass


# ============================================================
# АДМИН ОТПРАВИЛ ТЕКСТ ОТВЕТА
# ============================================================
@router.message(F.text & ~F.text.startswith("/"), _is_admin_waiting_reply)
async def handle_admin_reply(message: Message):
    if not _is_admin(message.from_user.id):
        return

    ticket_id = PENDING_ADMIN_REPLY.pop(message.from_user.id, None)
    if ticket_id is None:
        return

    reply_text = message.text.strip()[:2000]

    # Сохраняем в БД
    async with async_session() as session:
        ticket = (await session.execute(
            select(SupportTicket).where(SupportTicket.id == ticket_id)
        )).scalar_one_or_none()

        if ticket is None:
            await message.answer("Тикет не найден.")
            return

        if ticket.status == "closed":
            await message.answer("Тикет уже закрыт.")
            return

        from datetime import datetime
        ticket.admin_reply = reply_text
        ticket.admin_id = message.from_user.id
        ticket.status = "closed"
        ticket.closed_at = datetime.utcnow()

        user = (await session.execute(
            select(User).where(User.id == ticket.user_id)
        )).scalar_one_or_none()

        await session.commit()

    # Отправляем пользователю
    if user:
        try:
            await message.bot.send_message(
                user.telegram_id,
                f"💬 <b>Ответ поддержки</b>\n\n{reply_text}\n\n"
                f"<i>Если появятся вопросы — просто напиши снова.</i>"
            )
            await message.answer(
                f"✅ <b>Ответ отправлен</b> пользователю.\n\n"
                f"<b>Тикет #{ticket_id}</b> закрыт."
            )
        except Exception:
            logger.exception("Failed to deliver reply")
            await message.answer(
                "❌ Не удалось доставить ответ. Возможно, пользователь заблокировал бота."
            )
    else:
        await message.answer("Пользователь не найден в БД.")