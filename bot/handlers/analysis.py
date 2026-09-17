import io

from aiogram import F, Router
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from bot.handlers.start import get_or_create_user
from bot.keyboards.main import share_kb
from config import config
from database.connection import async_session
from database.models import PhotoAnalysis
from services.achievements import unlock_achievement
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


def _build_result_text(analysis: dict) -> str:
    scores = analysis.get("scores", {}) or {}
    return (
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


async def _trigger_post_analysis_hooks(bot, telegram_id: int) -> None:
    """Хуки монетизации: обязательная подписка + реклама."""
    try:
        from bot.handlers.subscriptions import maybe_offer_subscription
        await maybe_offer_subscription(bot, telegram_id)
    except Exception:
        logger.exception("Subscription offer hook failed")

    try:
        from services.advertising.broadcaster import maybe_send_ad
        await maybe_send_ad(bot, telegram_id)
    except Exception:
        logger.exception("Ad hook failed")


@router.message(F.photo)
async def handle_photo(message: Message):
    await message.answer("🔍 Анализирую твоё фото... Это займёт несколько секунд.")

    # 1. Скачиваем фото
    try:
        image_bytes = await _download_photo(message)
    except Exception:
        logger.exception("Download failed")
        await message.answer("😔 Не удалось скачать фото. Попробуй ещё раз.")
        return

    # 2. Анализ AI
    try:
        analysis = await analyze_photo(image_bytes)
    except Exception:
        logger.exception("Analysis failed")
        await message.answer("😔 AI сейчас не смог проанализировать фото. Попробуй позже.")
        return

    # 3. Сохраняем пользователя (на случай если он не жал /start)
    user = await get_or_create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
    )

    # 4. Сохраняем анализ + профиль
    async with async_session() as session:
        photo = message.photo[-1]
        session.add(PhotoAnalysis(
            user_id=user.id,
            telegram_file_id=photo.file_id,
            telegram_file_unique_id=photo.file_unique_id,
            analysis_json=analysis,
            model=config.GIGACHAT_MODEL,
            prompt_version=config.PROMPT_VERSION_PHOTO,
        ))
        profile = build_profile(user.id, analysis)
        session.add(profile)
        await session.commit()

    # 5. Достижения
    try:
        await unlock_achievement(user.id, "first_photo")
        scores = analysis.get("scores", {}) or {}
        if scores.get("chaos", 0) >= 90:
            await unlock_achievement(user.id, "chaos_90")
        if scores.get("charisma", 0) >= 90:
            await unlock_achievement(user.id, "charisma_90")
    except Exception:
        logger.exception("Achievement unlock failed")

    # 6. Текст результата
    result_text = _build_result_text(analysis)

    # 7. Карточка
    try:
        bot_username = (await message.bot.get_me()).username
        card_bytes = generate_card(analysis, message.from_user.username, bot_username)
        photo_input = BufferedInputFile(card_bytes, filename="card.png")
        await message.answer_photo(photo_input, caption=result_text)
    except Exception:
        logger.exception("Card generation failed")
        await message.answer(result_text)

    # 8. Share-кнопки
    bot_username = (await message.bot.get_me()).username
    share_url = f"https://t.me/{bot_username}?start=ref_{user.id}"
    share_text = analysis.get("share_text", "Мне AI выдал смешной профиль 😂 Проверь себя!")
    share_link = f"https://t.me/share/url?url={share_url}&text={share_text}"

    await message.answer(
        "📤 Поделись результатом с друзьями — пусть тоже пройдут анализ!",
        reply_markup=share_kb(share_link),
    )

    # 9. Хуки монетизации (подписка + реклама)
    await _trigger_post_analysis_hooks(message.bot, message.from_user.id)


@router.callback_query(F.data == "new_analysis")
async def cb_new_analysis(callback: CallbackQuery):
    await callback.answer()
    await callback.message.answer("📸 Отправь новое фото для анализа!")


@router.callback_query(F.data == "send_photo")
async def cb_send_photo(callback: CallbackQuery):
    await callback.answer()
    await callback.message.answer("📸 Просто отправь фото в чат!")