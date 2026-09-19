from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.filters import CommandStart, Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select

from bot.keyboards.main import main_menu_kb, send_photo_kb
from config import config
from database.connection import async_session
from database.models import User
from services.analytics.tracker import track
from services.feature_flags import is_enabled
from utils.logging import get_logger

router = Router()
logger = get_logger(__name__)


def _guess_timezone(language_code: str | None) -> str:
    mapping = {
        "ru": "Europe/Moscow",
        "uk": "Europe/Kiev",
        "be": "Europe/Minsk",
        "kk": "Asia/Almaty",
        "uz": "Asia/Tashkent",
        "az": "Asia/Baku",
        "hy": "Asia/Yerevan",
        "ka": "Asia/Tbilisi",
        "en": "UTC",
        "de": "Europe/Berlin",
        "fr": "Europe/Paris",
        "tr": "Europe/Istanbul",
    }
    return mapping.get((language_code or "").lower(), "Europe/Moscow")


async def get_or_create_user(
    telegram_id: int,
    username: str | None,
    first_name: str | None,
    referrer_id: int | None = None,
    language_code: str | None = None,
) -> User:
    async with async_session() as session:
        user = (await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )).scalar_one_or_none()

        if user is None:
            tz = _guess_timezone(language_code)

            user = User(
                telegram_id=telegram_id,
                username=username,
                first_name=first_name,
                is_admin=(telegram_id in config.ADMIN_IDS),
                referrer_id=referrer_id,
                timezone=tz,
                timezone_confirmed=False,
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
            logger.info(f"New user created: {telegram_id} ref={referrer_id} tz={tz}")

            await track("new_users", telegram_id=telegram_id)

            if referrer_id:
                await track(
                    "referral_completed",
                    telegram_id=telegram_id,
                    payload={"referrer_id": referrer_id},
                )
        else:
            user.last_active_at = datetime.now(timezone.utc)
            if username and user.username != username:
                user.username = username
            if first_name and user.first_name != first_name:
                user.first_name = first_name
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

    referrals_on = await is_enabled("referrals_enabled", default=True)

    if payload and payload.startswith("ref_") and referrals_on:
        try:
            referrer_id = int(payload.replace("ref_", ""))
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
        language_code=message.from_user.language_code,
    )

    text = (
        "👋 <b>Привет!</b>\n\n"
        "Я — AI-бот социальной игры.\n"
        "Отправь мне фотографию — и я сделаю тебе смешной игровой профиль, "
        "которым захочется поделиться.\n\n"
        "📸 <b>Просто отправь фото прямо в чат!</b>\n\n"
        "Кнопки внизу — профиль, поиск игроков, сравнение с друзьями, "
        "настройки и другое."
    )
    await message.answer(text, reply_markup=main_menu_kb())


@router.message(Command("help"))
async def cmd_help(message: Message):
    text = (
        "📖 <b>Что умеет бот</b>\n\n"
        "1️⃣ <b>Отправь фото</b> — получишь игровой AI-профиль.\n\n"
        "2️⃣ <b>Поделись результатом</b> — «📤 Поделиться».\n\n"
        "3️⃣ <b>Найди игроков</b> — «🎯 Найти игроков»: 7 режимов.\n\n"
        "4️⃣ <b>Пройди тесты</b> — «🧪 Пройти тест».\n\n"
        "5️⃣ <b>Сравни с другом</b> — «👥 Сравнить».\n\n"
        "6️⃣ <b>Собери достижения</b> — «🏆 Достижения».\n\n"
        "7️⃣ <b>PRO подписка</b> — «💎 PRO».\n\n"
        "🌍 <b>Часовой пояс</b> — настрой для удобных уведомлений.\n\n"
        "🆘 <b>Поддержка</b> — если что-то не работает."
    )
    await message.answer(text)


@router.message(F.text == "📸 Новый анализ")
async def new_analysis_hint(message: Message):
    await message.answer(
        "📸 <b>Новый анализ</b>\n\n"
        "Просто отправь мне своё фото прямо в чат — я всё сделаю сам.\n\n"
        "💡 <b>Совет:</b> лучше всего работают обычные фото, где видно "
        "лицо и настроение. Стикеры, рисунки и скриншоты не подойдут.",
        reply_markup=send_photo_kb(),
    )


@router.callback_query(F.data == "send_photo")
async def cb_send_photo(callback: CallbackQuery):
    await callback.answer()
    await callback.message.answer("📸 Просто отправь фото в чат!")


@router.callback_query(F.data == "back_to_main")
async def cb_back_to_main(callback: CallbackQuery):
    await callback.answer()
    await callback.message.answer("🏠 Главное меню", reply_markup=main_menu_kb())


@router.callback_query(F.data == "cancel_action")
async def cb_cancel(callback: CallbackQuery):
    await callback.answer("Отменено")
    await callback.message.answer("Действие отменено.", reply_markup=main_menu_kb())