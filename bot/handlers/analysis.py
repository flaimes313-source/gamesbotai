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
from database.models import PhotoAnalysis, Profile, User, UserAchievement
from services.achievements import unlock_achievement
from services.analytics.tracker import track
from services.analysis.photo_analysis import analyze_photo
from services.analysis.profile_builder import build_profile
from services.analysis.rarity import (
    LEGENDARY_ARCHETYPES,
    LEGENDARY_POINTS,
    is_legendary,
    maybe_make_legendary,
    mark_legendary_received,
)
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


def _build_result_text(analysis: dict, is_legendary: bool = False) -> str:
    """
    Собирает текст результата анализа.
    При is_legendary=True — добавляет плашку «✨ ЛЕГЕНДАРНЫЙ АРХЕТИП!».
    """
    scores = analysis.get("scores", {}) or {}

    if is_legendary:
        header = f"✨🔥 <b>ЛЕГЕНДАРНЫЙ АРХЕТИП!</b> 🔥✨\n\n🧨 <b>{analysis.get('archetype', 'ТВОЙ АРХЕТИП')}</b>"
    else:
        header = f"🧨 <b>{analysis.get('archetype', 'ТВОЙ АРХЕТИП')}</b>"

    return (
        f"{header}\n\n"
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


async def _get_achievement_badges(user_id: int) -> list:
    async with async_session() as session:
        rows = (await session.execute(
            select(UserAchievement)
            .where(UserAchievement.user_id == user_id)
            .order_by(UserAchievement.unlocked_at.desc())
            .limit(3)
        )).scalars().all()

    return [a.achievement_code for a in rows]


async def _count_unique_legendaries(user_id: int) -> int:
    """
    Считает, сколько РАЗНЫХ легендарных архетипов уже собрал юзер.
    Читает profiles.archetype и фильтрует по списку LEGENDARY_ARCHETYPES.
    Используется для достижения five_legendaries.
    """
    async with async_session() as session:
        rows = (await session.execute(
            select(Profile.archetype).where(Profile.user_id == user_id)
        )).scalars().all()

    seen = set()
    for arch in rows:
        if arch and is_legendary(arch):
            seen.add(arch.strip().upper())
    return len(seen)


async def _handle_legendary_achievements(user_id: int, telegram_id: int) -> None:
    """
    Триггерит достижения за легендарку:
    - first_legendary — если это первая.
    - five_legendaries — если собрано >= 5 разных.
    Безопасно: любая ошибка логируется, но не валит поток.
    """
    try:
        unique_count = await _count_unique_legendaries(user_id)

        if unique_count >= 1:
            newly = await unlock_achievement(user_id, "first_legendary")
            if newly:
                await track(
                    "legendary_achievement",
                    telegram_id=telegram_id,
                    payload={"code": "first_legendary", "unique_count": unique_count},
                )

        if unique_count >= 5:
            newly = await unlock_achievement(user_id, "five_legendaries")
            if newly:
                await track(
                    "legendary_achievement",
                    telegram_id=telegram_id,
                    payload={"code": "five_legendaries", "unique_count": unique_count},
                )
    except Exception:
        logger.exception("Legendary achievements failed")


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

    # Скачиваем фото
    try:
        image_bytes = await _download_photo(message)
    except Exception:
        logger.exception("Download failed")
        await message.answer("😔 Не удалось скачать фото. Попробуй ещё раз.")
        return

    await track("analysis_started", telegram_id=telegram_id)

    # A/B-тест промта
    variant = await get_variant("photo_prompt", telegram_id)
    prompt_override, prompt_version = pick_prompt_by_variant(variant)
    logger.info(f"A/B: user={telegram_id} variant={variant} prompt={prompt_version}")

    # Анализ AI
    try:
        analysis = await analyze_photo(image_bytes, prompt_override=prompt_override)
    except Exception:
        logger.exception("Analysis failed")
        await message.answer("😔 AI сейчас не смог проанализировать фото. Попробуй позже.")
        return

    await track("analysis_completed", telegram_id=telegram_id)

    # ============================================================
    # РЕДКОСТЬ: возможно, подменим архетип на легендарный
    # ============================================================
    original_archetype = analysis.get("archetype", "")
    try:
        final_archetype, is_legendary_flag = await maybe_make_legendary(
            user.id, original_archetype
        )
    except Exception:
        logger.exception("maybe_make_legendary failed")
        final_archetype, is_legendary_flag = original_archetype, False

    if is_legendary_flag:
        # Подменяем архетип во всём analysis, чтобы и в БД, и на карточке,
        # и в тексте, и в share-тексте было одно и то же имя.
        analysis["archetype"] = final_archetype

    # Сохраняем
    async with async_session() as session:
        photo = message.photo[-1]
        session.add(PhotoAnalysis(
            user_id=user.id,
            telegram_file_id=photo.file_id,
            telegram_file_unique_id=photo.file_unique_id,
            analysis_json=analysis,
            model=getattr(config, "GIGACHAT_VISION_MODEL", config.GIGACHAT_MODEL),
            prompt_version=prompt_version,
        ))
        profile = build_profile(user.id, analysis)
        session.add(profile)
        await session.commit()

    # Вовлечение: анализ + новый архетип + челлендж
    engagement_result = {}
    try:
        from services.engagement.service import on_photo_analyzed
        engagement_result = await on_photo_analyzed(user.id, analysis.get("archetype", ""))
    except Exception:
        logger.exception("Engagement on_photo_analyzed failed")

    # ============================================================
    # Легендарка: события, очки, cooldown, достижения
    # ============================================================
    if is_legendary_flag:
        # Событие: выпала легендарка
        try:
            await track(
                "legendary_archetype",
                telegram_id=telegram_id,
                payload={
                    "archetype": final_archetype,
                    "replaced_from": original_archetype,
                },
            )
        except Exception:
            logger.exception("track legendary_archetype failed")

        # Очки за легендарку (вместо обычных 30 за new_archetype —
        # начисляем дополнительно, чтобы не ломать on_photo_analyzed)
        try:
            from services.engagement.points import add_custom_points
            await add_custom_points(user.id, LEGENDARY_POINTS)
        except Exception:
            logger.exception("add_custom_points legendary failed")

        # Обновляем cooldown: last_legendary_at = now
        try:
            await mark_legendary_received(user.id)
        except Exception:
            logger.exception("mark_legendary_received failed")

    # ⭐ РЕФЕРАЛЬНАЯ НАГРАДА: если у юзера есть referrer — начислить ему
    try:
        from services.engagement.referrals import on_referred_user_analyzed
        await on_referred_user_analyzed(user.id)
    except Exception:
        logger.exception("Referral reward failed")

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

    # Легендарные достижения — отдельно, после базовых
    if is_legendary_flag:
        await _handle_legendary_achievements(user.id, telegram_id)

    # Текст результата
    result_text = _build_result_text(analysis, is_legendary=is_legendary_flag)

    bot_username = (await message.bot.get_me()).username
    share_url = f"https://t.me/{bot_username}?start=ref_{user.id}"

    archetype = analysis.get("archetype", "")

    # Для легендарки — особый share-призыв вместо общего pick_share_call
    if is_legendary_flag:
        share_call = (
            "🔥 Мне выпал ЛЕГЕНДАРНЫЙ архетип! "
            "Проверь свой вайб — вдруг ты тоже?"
        )
    else:
        share_call = pick_share_call(archetype)

    full_caption = (
        f"{result_text}\n\n"
        f"───────────────────\n"
        f"{share_call}\n\n"
        f"👉 <b>Проверь себя:</b> {share_url}"
    )

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

    if engagement_result.get("is_new_archetype"):
        full_caption += "\n\n✨ <b>Новый архетип в коллекции!</b>"

    if is_legendary_flag:
        full_caption += "\n\n🌟 <b>+300 очков за легендарный архетип!</b>"

    # Карточка
    try:
        achievements_codes = await _get_achievement_badges(user.id)
        analysis_with_badges = dict(analysis)
        analysis_with_badges["achievements"] = achievements_codes

        card_bytes = generate_card(
            analysis_with_badges,
            message.from_user.username,
            bot_username,
            is_legendary=is_legendary_flag,
        )
        photo_input = BufferedInputFile(card_bytes, filename="card.png")
        await message.answer_photo(
            photo_input,
            caption=full_caption,
            reply_markup=share_kb(share_url),
        )
    except Exception:
        logger.exception("Card generation failed")
        await message.answer(full_caption, reply_markup=share_kb(share_url))

    # Уведомление о челлендже
    challenge_result = engagement_result.get("challenge") or {}
    if challenge_result.get("completed"):
        try:
            await message.answer(
                "🎯 <b>Челлендж дня выполнен!</b>\n\n"
                f"Награда: +{challenge_result.get('reward_points', 50)} очков"
            )
        except Exception:
            pass

    await track("share_generated", telegram_id=telegram_id)
    await _trigger_post_analysis_hooks(message.bot, telegram_id)

    # Отправляем накопленные уведомления
    try:
        from services.engagement.notifications import flush_notifications
        await flush_notifications(message.bot, telegram_id)
    except Exception:
        logger.exception("flush_notifications failed")


# ============================================================
# Кнопка «Поделиться»
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

        profile = (await session.execute(
            select(Profile)
            .where(Profile.user_id == user.id)
            .order_by(Profile.id.desc())
            .limit(1)
        )).scalar_one_or_none()
        profile_archetype = profile.archetype if profile else None

    bot_username = (await callback.bot.get_me()).username
    share_url = f"https://t.me/{bot_username}?start=ref_{user.id}"

    # Если последний архетип — легендарный, особый share-призыв
    if profile_archetype and is_legendary(profile_archetype):
        share_call = (
            "🔥 Мне выпал ЛЕГЕНДАРНЫЙ архетип! "
            "Проверь свой вайб — вдруг ты тоже?"
        )
    else:
        share_call = pick_share_call(profile_archetype)

    share_text = f"Мне AI выдал смешной профиль 😂 {share_call}"
    share_link = f"https://t.me/share/url?url={share_url}&text={share_text}"

    await track("share_clicked", telegram_id=callback.from_user.id)

    try:
        from services.engagement.service import on_share
        await on_share(user.id)
    except Exception:
        logger.exception("Engagement on_share failed")

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

    try:
        from services.engagement.notifications import flush_notifications
        await flush_notifications(callback.bot, callback.from_user.id)
    except Exception:
        logger.exception("flush_notifications failed")


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