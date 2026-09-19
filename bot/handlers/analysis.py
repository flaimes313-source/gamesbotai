import io

from aiogram import F, Router
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy import func, select

from bot.handlers.start import get_or_create_user
from bot.keyboards.main import share_kb
from config import config
from database.connection import async_session
from database.models import PhotoAnalysis, User
from services.achievements import unlock_achievement
from services.analytics.tracker import track
from services.analysis.photo_analysis import analyze_photo
from services.analysis.profile_builder import build_profile
from services.cards.generator import generate_card
from services.experiments import get_variant, pick_prompt_by_variant
from services.rate_limit import check_and_increment
from services.share_calls import pick_share_call
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
    try:
        from services.advertising.broadcaster import maybe_send_ad
        await maybe_send_ad(bot, telegram_id)
    except Exception:
        logger.exception("Ad hook failed")


@router.message(F.photo)
async def handle_photo(message: Message):
    telegram_id = message.from_user.id

    await message.answer("🔍 Анализирую твоё фото... Это займёт несколько секунд.")
    await track("photo_sent", telegram_id=telegram_id)

    user = await get_or_create_user(
        telegram_id=telegram_id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
    )

    # Rate limit
    allowed, used, limit = await check_and_increment(telegram_id, user.id)
    if not allowed:
        await message.answer(
            f"⚠️ Ты достиг дневного лимита AI-анализов ({used}/{limit}).\n\n"
            "💎 С PRO можно делать до 50 анализов в день.\n"
            "Лимит обновится завтра."
        )
        return

    logger.info(f"AI usage: user={user.id} {used}/{limit}")

    # Скачиваем
    try:
        image_bytes = await _download_photo(message)
    except Exception:
        logger.exception("Download failed")
        await message.answer("😔 Не удалось скачать фото. Попробуй ещё раз.")
        return

    await track("analysis_started", telegram_id=telegram_id)

    # A/B промт
    variant = await get_variant("photo_prompt", telegram_id)
    prompt_override, prompt_version = pick_prompt_by_variant(variant)
    logger.info(f"A/B: user={telegram_id} variant={variant} prompt={prompt_version}")

    # AI
    try:
        analysis = await analyze_photo(image_bytes, prompt_override=prompt_override)
    except Exception:
        logger.exception("Analysis failed")
        await message.answer("😔 AI сейчас не смог проанализировать фото. Попробуй позже.")
        return

    await track("analysis_completed", telegram_id=telegram_id)

    # Сохраняем
    async with async_session() as session:
        photo = message.photo[-1]
        session.add(PhotoAnalysis(
            user_id=user.id,
            telegram_file_id=photo.file_id,
            telegram_file_unique_id=photo.file_unique_id,
            analysis_json=analysis,
            model=config.GIGACHAT_MODEL,
            prompt_version=prompt_version,
        ))
        profile = build_profile(user.id, analysis)
        session.add(profile)
        await session.commit()

    # Достижения
    try:
        await unlock_achievement(user.id, "first_photo")
        scores = analysis.get("scores", {}) or {}
        if scores.get("chaos", 0) >= 90:
            await unlock_achievement(user.id, "chaos_90")
        if scores.get("charisma", 0) >= 90:
            await unlock_achievement(user.id, "charisma_90")

        async with async_session() as session:
            cnt = (await session.execute(
                select(func.count(PhotoAnalysis.id)).where(PhotoAnalysis.user_id == user.id)
            )).scalar_one()
            if cnt == 2:
                await track("second_analysis", telegram_id=telegram_id)
            if cnt >= 5:
                await unlock_achievement(user.id, "five_analyses")
    except Exception:
        logger.exception("Achievement unlock failed")

    # Результат + share-текст
    result_text = _build_result_text(analysis)

    bot_username = (await message.bot.get_me()).username
    share_url = f"https://t.me/{bot_username}?start=ref_{user.id}"

    # Персональный призыв по архетипу
    archetype = analysis.get("archetype", "")
    share_call = pick_share_call(archetype)

    full_caption = (
        f"{result_text}\n\n"
        f"───────────────────\n"
        f"{share_call}\n\n"
        f"👉 <b>Проверь себя:</b> {share_url}"
    )

    # Обрезаем под лимит caption (1024)
    if len(full_caption) > 1024:
        overhead = len(share_call) + len(share_url) + 100
        allowed_result_len = max(200, 1024 - overhead)
        result_text_short = result_text[:allowed_result_len] + "…"
        full_caption = (
            f"{result_text_short}\n\n"
            f"───────────────────\n"
            f"{share_call}\n\n"
            f"👉 <b>Проверь себя:</b> {share_url}"
        )

    # Карточка + caption
    try:
        card_bytes = generate_card(analysis, message.from_user.username, bot_username)
        photo_input = BufferedInputFile(card_bytes, filename="card.png")
        await message.answer_photo(
            photo_input,
            caption=full_caption,
            reply_markup=share_kb(share_url),
        )
    except Exception:
        logger.exception("Card generation failed")
        await message.answer(full_caption, reply_markup=share_kb(share_url))

    await track("share_generated", telegram_id=telegram_id)
    await _trigger_post_analysis_hooks(message.bot, telegram_id)


# ============================================================
# Кнопка «Поделиться» — инструкция + ссылка
# ============================================================
@router.callback_query(F.data == "do_share")
async def cb_do_share(callback: CallbackQuery):
    await callback.answer()

    async with async_session() as session:
        user = (await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )).scalar_one_or_none()

        if user is None:
            await callback.message.answer("Сначала отправь фото!")
            return

        # Последний профиль для архетипа
        profile_archetype = None
        from database.models import Profile
        profile = (await session.execute(
            select(Profile)
            .where(Profile.user_id == user.id)
            .order_by(Profile.id.desc())
            .limit(1)
        )).scalar_one_or_none()
        if profile:
            profile_archetype = profile.archetype

    bot_username = (await callback.bot.get_me()).username
    share_url = f"https://t.me/{bot_username}?start=ref_{user.id}"

    # Персональный призыв
    share_call = pick_share_call(profile_archetype)

    share_text = f"Мне AI выдал смешной профиль 😂 {share_call}"
    share_link = f"https://t.me/share/url?url={share_url}&text={share_text}"

    await track("share_clicked", telegram_id=callback.from_user.id)

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="📤 Отправить ссылку в Telegram",
                url=share_link,
            )],
            [InlineKeyboardButton(
                text="📋 Скопировать ссылку",
                callback_data=f"copy_link_{user.id}",
            )],
            [InlineKeyboardButton(
                text="👥 Мои чаты",
                callback_data="chat_list",
            )],
        ]
    )

    await callback.message.answer(
        "📤 <b>Как поделиться с друзьями</b>\n\n"
        "<b>Вариант 1 — со своей карточкой (рекомендую):</b>\n"
        "1️⃣ Нажми на <b>карточку выше</b> и удерживай её.\n"
        "2️⃣ Выбери <b>«Переслать»</b> (Forward).\n"
        "3️⃣ Выбери друга — он получит <b>карточку + текст + ссылку</b>.\n\n"
        "<b>Вариант 2 — только ссылка:</b>\n"
        "Отправь другу ссылку ниже 👇\n\n"
        f"<code>{share_url}</code>\n\n"
        f"<i>{share_call}</i>",
        reply_markup=kb,
    )


@router.callback_query(F.data.startswith("copy_link_"))
async def cb_copy_link(callback: CallbackQuery):
    await callback.answer("Ссылка скопирована!")
    user_id = int(callback.data.replace("copy_link_", ""))
    bot_username = (await callback.bot.get_me()).username
    share_url = f"https://t.me/{bot_username}?start=ref_{user_id}"
    await callback.message.answer(f"<code>{share_url}</code>")


@router.callback_query(F.data == "new_analysis")
async def cb_new_analysis(callback: CallbackQuery):
    await callback.answer()
    await callback.message.answer("📸 Отправь новое фото для анализа!")


@router.callback_query(F.data == "send_photo")
async def cb_send_photo(callback: CallbackQuery):
    await callback.answer()
    await callback.message.answer("📸 Просто отправь фото в чат!")