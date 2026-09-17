from aiogram import F, Router
from aiogram.types import Message, CallbackQuery
from sqlalchemy import select

from bot.keyboards.profile import profile_kb
from database.connection import async_session
from database.models import Profile, User
from utils.logging import get_logger

router = Router()
logger = get_logger(__name__)


async def _latest_profile(telegram_id: int) -> tuple[User | None, Profile | None]:
    async with async_session() as session:
        user = (await session.execute(select(User).where(User.telegram_id == telegram_id))).scalar_one_or_none()
        if user is None:
            return None, None
        profile = (
            await session.execute(
                select(Profile).where(Profile.user_id == user.id).order_by(Profile.id.desc()).limit(1)
            )
        ).scalar_one_or_none()
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


@router.message(F.text == "👤 Мой профиль")
async def show_profile(message: Message):
    user, profile = await _latest_profile(message.from_user.id)
    if profile is None:
        await message.answer("У тебя пока нет профиля. Отправь фото 📸 чтобы пройти первый анализ!")
        return
    await message.answer(_profile_text(user, profile), reply_markup=profile_kb())


@router.callback_query(F.data == "share_profile")
async def cb_share(callback: CallbackQuery):
    await callback.answer()
    user, profile = await _latest_profile(callback.from_user.id)
    if profile is None:
        await callback.message.answer("Сначала пройди анализ — отправь фото!")
        return
    bot_username = (await callback.bot.get_me()).username
    share_url = f"https://t.me/{bot_username}?start=ref_{user.id}"
    await callback.message.answer(
        f"Твоя ссылка для друзей:\n{share_url}\n\nСкинь им — пусть сравнят себя с тобой 😂"
    )


@router.callback_query(F.data == "settings")
async def cb_settings(callback: CallbackQuery):
    await callback.answer("Настройки появятся в следующем обновлении 🙂")