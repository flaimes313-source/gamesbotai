from aiogram import F, Router
from aiogram.filters import CommandStart, Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select

from bot.keyboards.main import main_menu_kb
from config import config
from database.connection import async_session
from database.models import User
from services.analytics.tracker import track
from utils.logging import get_logger

router = Router()
logger = get_logger(__name__)


async def get_or_create_user(
    telegram_id: int,
    username: str | None,
    first_name: str | None,
    referrer_id: int | None = None,
) -> User:
    async with async_session() as session:
        user = (
            await session.execute(select(User).where(User.telegram_id == telegram_id))
        ).scalar_one_or_none()

        if user is None:
            user = User(
                telegram_id=telegram_id,
                username=username,
                first_name=first_name,
                is_admin=(telegram_id in config.ADMIN_IDS),
                referrer_id=referrer_id,
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            logger.info(f"New user created: {telegram_id} ref={referrer_id}")

            # Трекаем
            await track("new_users", telegram_id=telegram_id)
            if referrer_id:
                await track(
                    "referral_completed",
                    telegram_id=telegram_id,
                    payload={"referrer_id": referrer_id},
                )
        else:
            # Обновляем last_active_at
            user.last_active_at = __import__("datetime").datetime.utcnow()
            await session.commit()

        return user


@router.message(CommandStart())
async def cmd_start(message: Message):
    payload = None
    if message.text and " " in message.text:
        args = message.text.split(maxsplit=1)
        if len(args) > 1:
            payload = args[1].strip()

    referrer_id = None
    if payload and payload.startswith("ref_") and config.REFERRALS_ENABLED:
        try:
            referrer_id = int(payload.replace("ref_", ""))
            # Открытие реферальной ссылки
            await track(
                "referral_opened",
                telegram_id=message.from_user.id,
                payload={"referrer_id": referrer_id},
            )
        except ValueError:
            referrer_id = None

    await get_or_create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        referrer_id=referrer_id,
    )

    text = (
        "👋 Привет!\n\n"
        "Я — AI-бот социальной игры.\n"
        "Отправь мне фотографию — и я сделаю тебе смешной игровой профиль, "
        "которым захочется поделиться.\n\n"
        "📸 Просто отправь фото прямо в чат!"
    )
    await message.answer(text, reply_markup=main_menu_kb())


@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "Отправь фото — получишь свой игровой AI-профиль.\n"
        "Кнопки внизу — профиль, сравнение, поиск игроков, настройки."
    )