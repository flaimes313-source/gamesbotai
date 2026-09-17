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


# ============================================================
# Фильтр: срабатываем ТОЛЬКО если пользователь ждёт отправки тикета
# ============================================================
def _is_waiting_ticket(message: Message) -> bool:
    return PENDING_TICKET.get(message.from_user.id, False)


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


# ============================================================
# REPLY-КНОПКА «🆘 Поддержка»
# ============================================================
@router.message(F.text == "🆘 Поддержка")
async def support_from_menu(message: Message):
    logger.info(f"Support button pressed by {message.from_user.id}")
    await message.answer(
        "🆘 <b>Поддержка</b>\n\n"
        "Выбери действие:",
        reply_markup=support_menu_kb(),
    )


# ============================================================
# CALLBACK-И
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
        "✍️ Напиши свой вопрос одним сообщением.\n"
        "Мы передадим его в поддержку, и ответ придёт сюда же.\n\n"
        "Чтобы отменить — отправь /cancel"
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


# ============================================================
# /cancel — отмена тикета
# ============================================================
@router.message(F.text == "/cancel")
async def cmd_cancel(message: Message):
    if PENDING_TICKET.pop(message.from_user.id, False):
        await message.answer("❌ Отменено. Тикет не создан.")
    else:
        await message.answer("Нечего отменять.")


# ============================================================
# CATCH-ALL — срабатывает ТОЛЬКО при активном ожидании тикета
# ============================================================
@router.message(F.text & ~F.text.startswith("/"), _is_waiting_ticket)
async def handle_support_message(message: Message):
    if not PENDING_TICKET.get(message.from_user.id):
        return

    PENDING_TICKET.pop(message.from_user.id, None)

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

    await message.answer(
        f"✅ <b>Тикет #{ticket.id} создан.</b>\n\n"
        f"Ответ придёт сюда от администратора."
    )

    for admin_id in config.ADMIN_IDS:
        try:
            await message.bot.send_message(
                admin_id,
                f"🆘 <b>Новый тикет #{ticket.id}</b>\n\n"
                f"От: {message.from_user.first_name} (@{message.from_user.username or '—'})\n\n"
                f"{message.text[:500]}"
            )
        except Exception:
            logger.exception(f"Failed to notify admin {admin_id}")