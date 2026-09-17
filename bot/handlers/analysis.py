import io

from aiogram import F, Router
from aiogram.types import Message, BufferedInputFile, CallbackQuery
from sqlalchemy import select

from bot.keyboards.main import share_kb
from bot.handlers.start import get_or_create_user
from config import config
from database.connection import async_session
from database.models import PhotoAnalysis, Profile, User
from services.analysis.photo_analysis import analyze_photo
from services.analysis.profile_builder import build_profile
from services.cards.generator import generate_card
from utils.logging import get_logger

router = Router()
logger = get_logger(__name__)


async def _download_photo(message: Message) -> bytes:
    photo = message.photo[-1]
    file = await message.bot.get_file(photo.file_id)
    buf = io.BytesIO()
    await message.bot.download_file(file.file_path, buf)
    return buf.getvalue()


@router.message(F.photo)
async def handle_photo(message: Message):
    await message.answer("🔍 Анализирую твоё фото... Это займёт несколько секунд.")

    try:
        image_bytes = await _download_photo(message)
    except Exception as e:
        logger.exception("Download failed")
        await message.answer("😔 Не удалось скачать фото. Попробуй ещё раз.")
        return

    try:
        analysis = await analyze_photo(image_bytes)
    except Exception as e:
        logger.exception("Analysis failed")
        await message.answer("😔 AI сейчас не смог проанализировать фото. Попробуй позже.")
        return

    # Сохраняем пользователя (на случай если он не жал /start)
    user = await get_or_create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
    )

    async with async_session() as session:
        # сохраняем анализ
        photo = message.photo[-1]
        analysis_row = PhotoAnalysis(
            user_id=user.id,
            telegram_file_id=photo.file_id,
            telegram_file_unique_id=photo.file_unique_id,
            analysis_json=analysis,
            model=config.GIGACHAT_MODEL,
            prompt_version=config.PROMPT_VERSION_PHOTO,
        )
        session.add(analysis_row)

        # сохраняем профиль
        profile = build_profile(user.id, analysis)
        session.add(profile)

        await session.commit()

    # Собираем текст результата
    scores = analysis.get("scores", {})
    result_text = (
        f"🧨 <b>{analysis.get('archetype', 'ТВОЙ АРХЕТИП')}</b>\n\n"
        f"{analysis.get('short_description', '')}\n\n"
        f"Харизма: <b>{scores.get('charisma', 0)}</b>/100\n"
        f"Уверенность: <b>{scores.get('confidence', 0)}</b>/100\n"
        f"Юмор: <b>{scores.get('humor', 0)}</b>/100\n"
        f"Энергия: <b>{scores.get('energy', 0)}</b>/100\n"
        f"Хаос: <b>{scores.get('chaos', 0)}</b>/100\n"
        f"Креативность: <b>{scores.get('creativity', 0)}</b>/100\n\n"
        f"⚠️ Опасность для друзей: <b>{analysis.get('danger_level', 0)}</b>/100\n\n"
        f"<i>Особый талант:</i> {analysis.get('funny_trait', '')}"
    )

    # Генерируем карточку
    try:
        card_bytes = generate_card(analysis, message.from_user.username)
        photo_input = BufferedInputFile(card_bytes, filename="card.png")
        await message.answer_photo(photo_input, caption=result_text)
    except Exception:
        logger.exception("Card generation failed")
        await message.answer(result_text)

    # Кнопка "поделиться"
    bot_username = (await message.bot.get_me()).username
    share_url = f"https://t.me/{bot_username}?start=ref_{user.id}"
    share_text = analysis.get("share_text", "Мне AI выдал смешной профиль 😂 Проверь себя!")
    share_link = f"https://t.me/share/url?url={share_url}&text={share_text}"

    await message.answer(
        "📤 Поделись результатом с друзьями — пусть тоже пройдут анализ!",
        reply_markup=share_kb(share_link),
    )


@router.callback_query(F.data == "new_analysis")
async def cb_new_analysis(callback: CallbackQuery):
    await callback.answer()
    await callback.message.answer("📸 Отправь новое фото для анализа!")