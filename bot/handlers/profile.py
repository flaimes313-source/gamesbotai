from aiogram import F, Router
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select

from bot.keyboards.main import share_link_kb
from bot.keyboards.profile import profile_kb
from database.connection import async_session
from database.models import Profile, User
from services.analytics.tracker import track
from utils.logging import get_logger

router = Router()
logger = get_logger(__name__)


async def _latest_profile(telegram_id: int) -> tuple[User | None, Profile | None]:
    async with async_session() as session:
        user = (await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )).scalar_one_or_none()
        if user is None:
            return None, None
        profile = (await session.execute(
            select(Profile).where(Profile.user_id == user.id)
            .order_by(Profile.id.desc()).limit(1)
        )).scalar_one_or_none()
        return user, profile


def _profile_text(user: User, profile: Profile) -> str:
    return (
        f"👤 <b>МОЙ ПРОФИЛЬ</b>\n\n"
        f"🧨 <b>{profile.archetype}</b>\n\n"
        f"Харизма {profile.charisma}\n"
        f"Уверенность {profile.confidence}\n"
        f"Юмор {profile.humor}\n"
        f"Энергия {profile.energy}\n"
        f"Интеллект {profile.intellect}\n"
        f"Креативность {profile.creativity}\n"
        f"Хаос {profile.chaos}\n\n"
        f"⚠️ Опасность для друзей: {profile.danger_level}\n\n"
        f"<i>{profile.vibe or ''}</i>"
    )


async def _send_share_link(bot, telegram_id: int, message_or_callback) -> None:
    """
    Общая логика для reply-кнопки «📤 Поделиться» и callback share_profile.
    """
    async with async_session() as session:
        user = (await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )).scalar_one_or_none()

    if user is None:
        text = "Сначала отправь фото — пусть появится профиль, которым можно поделиться!"
        if isinstance(message_or_callback, CallbackQuery):
            await message_or_callback.message.answer(text)
        else:
            await message_or_callback.answer(text)
        return

    bot_username = (await bot.get_me()).username
    share_url = f"https://t.me/{bot_username}?start=ref_{user.id}"
    share_text = "Мне AI выдал смешной профиль 😂 Проверь себя!"
    share_link = f"https://t.me/share/url?url={share_url}&text={share_text}"

    await track("share_clicked", telegram_id=telegram_id)

    text = (
        "📤 <b>Поделись результатом</b>\n\n"
        "Нажми кнопку ниже — откроется системный шаринг Telegram.\n"
        "Или скопируй ссылку и отправь другу:\n\n"
        f"<code>{share_url}</code>"
    )

    if isinstance(message_or_callback, CallbackQuery):
        await message_or_callback.message.answer(text, reply_markup=share_link_kb(share_link))
    else:
        await message_or_callback.answer(text, reply_markup=share_link_kb(share_link))


# ============================================================
# REPLY-КНОПКИ (постоянное меню)
# ============================================================
@router.message(F.text == "👤 Мой профиль")
async def show_profile(message: Message):
    user, profile = await _latest_profile(message.from_user.id)
    if profile is None:
        await message.answer("У тебя пока нет профиля. Отправь фото 📸 чтобы пройти первый анализ!")
        return
    await message.answer(_profile_text(user, profile), reply_markup=profile_kb())


@router.message(F.text == "📤 Поделиться")
async def share_from_menu(message: Message):
    await _send_share_link(message.bot, message.from_user.id, message)


@router.message(F.text == "⚙️ Настройки")
async def settings_from_menu(message: Message):
    from bot.keyboards.main import settings_kb
    await message.answer("⚙️ Настройки:", reply_markup=settings_kb())


# ============================================================
# CALLBACK-ХЕНДЛЕРЫ
# ============================================================
@router.callback_query(F.data == "share_profile")
async def cb_share(callback: CallbackQuery):
    await callback.answer()
    await _send_share_link(callback.bot, callback.from_user.id, callback)


@router.callback_query(F.data == "settings")
async def cb_settings(callback: CallbackQuery):
    await callback.answer()
    from bot.keyboards.main import settings_kb
    await callback.message.answer("⚙️ Настройки:", reply_markup=settings_kb())


@router.callback_query(F.data == "back_to_main")
async def cb_back_to_main(callback: CallbackQuery):
    await callback.answer()
    from bot.keyboards.main import main_menu_kb
    await callback.message.answer("🏠 Главное меню", reply_markup=main_menu_kb())