from datetime import datetime

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select

from config import config
from database.connection import async_session
from database.models import SupportTicket, User
from utils.logging import get_logger

router = Router()
logger = get_logger(__name__)


# Ожидание текста тикета: telegram_id → True
PENDING_TICKET: dict[int, bool] = {}


def support_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✍️ Написать в поддержку", callback_data="support_write")],
            [InlineKeyboardButton(text="📖 FAQ", callback_data="support_faq")],
        ]
    )


def faq_back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="support_menu")],
        ]
    )


@router.message(F.text == "🆘 Поддержка")
async def support_msg(message: Message):
    await message.answer(
        "🆘 <b>Поддержка</b>\n\n"
        "Выбери действие:",
        reply_markup=support_menu_kb(),
    )


@router.callback_query(F.data == "support_menu")
async def cb_support_menu(callback: CallbackQuery):
    await callback.answer()
    await callback.message.edit_text(
        "🆘 <b>Поддержка</b>\n\nВыбери действие:",
        reply_markup=support_menu_kb(),
    )


@router.callback_query(F.data == "support_write")
async def cb_support_write(callback: CallbackQuery):
    await callback.answer()
    PENDING_TICKET[callback.from_user.id] = True
    await callback.message.answer(
        "✍️ Напиши свой вопрос одним сообщением.\n"
        "Мы передадим его в поддержку, и ответ придёт сюда же."
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
        "🎯 Найти игроков → выбери режим поиска.\n\n"
        "<b>Как выйти из игры?</b>\n"
        "🎮 Социальная игра → Выйти из игры.\n\n"
        "<b>Как удалить данные?</b>\n"
        "Напиши в поддержку — удалим."
    )
    try:
        await callback.message.edit_text(text, reply_markup=faq_back_kb())
    except Exception:
        await callback.message.answer(text, reply_markup=faq_back_kb())


@router.message(F.text & ~F.text.startswith("/"))
async def handle_support_message(message: Message):
    if not PENDING_TICKET.get(message.from_user.id):
        return  # не наш случай

    PENDING_TICKET.pop(message.from_user.id, None)

    async with async_session() as session:
        user = (await session.execute(
            select(User).where(User.telegram_id == message.from_user.id)
        )).scalar_one_or_none()

        if user is None:
            # Создаём пользователя, если ещё нет
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
        f"✅ Тикет #{ticket.id} создан.\n"
        "Ответ придёт в этот чат от админа."
    )

    # Уведомляем админов
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