from aiogram import F, Router
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select

from bot.keyboards.timezone import timezone_menu_kb
from database.connection import async_session
from database.models import User
from services.timezones import format_local_time, get_local_now
from utils.logging import get_logger

router = Router()
logger = get_logger(__name__)


async def send_timezone_menu(message_or_callback, telegram_id: int, page: int = 0):
    text = (
        "🌍 <b>Выбери свой часовой пояс</b>\n\n"
        "От этого зависит:\n"
        "• когда приходить «результату дня»\n"
        "• когда не беспокоить тебя уведомлениями\n"
        "• как показывать время сообщений\n\n"
        "Выбери свой регион:"
    )
    kb = timezone_menu_kb(page=page)

    if isinstance(message_or_callback, CallbackQuery):
        try:
            await message_or_callback.message.edit_text(text, reply_markup=kb)
        except Exception:
            await message_or_callback.message.answer(text, reply_markup=kb)
    else:
        await message_or_callback.answer(text, reply_markup=kb)


@router.message(F.text == "🌍 Часовой пояс")
async def tz_from_menu(message: Message):
    await send_timezone_menu(message, message.from_user.id)


@router.callback_query(F.data == "tz_menu")
async def cb_tz_menu(callback: CallbackQuery):
    await callback.answer()
    await send_timezone_menu(callback, callback.from_user.id)


@router.callback_query(F.data.startswith("tz_page_"))
async def cb_tz_page(callback: CallbackQuery):
    await callback.answer()
    page = int(callback.data.replace("tz_page_", ""))
    await send_timezone_menu(callback, callback.from_user.id, page=page)


@router.callback_query(F.data.startswith("tz_set_"))
async def cb_tz_set(callback: CallbackQuery):
    await callback.answer("Сохраняю...")
    tz_name = callback.data.replace("tz_set_", "")

    async with async_session() as session:
        user = (await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )).scalar_one_or_none()

        if user is None:
            await callback.message.answer("Сначала отправь фото!")
            return

        user.timezone = tz_name
        user.timezone_confirmed = True
        await session.commit()

    # Проверяем, что зона валидная — берём текущее время
    local_time = format_local_time(tz_name, "%H:%M")
    local_date = get_local_now(tz_name).strftime("%d.%m.%Y")

    logger.info(f"TZ set: user={user.id} tz={tz_name}")

    await callback.message.answer(
        f"✅ <b>Часовой пояс сохранён</b>\n\n"
        f"🌍 {tz_name}\n"
        f"🕐 Сейчас у тебя: <b>{local_time}</b> ({local_date})\n\n"
        f"Теперь уведомления будут приходить в удобное время."
    )