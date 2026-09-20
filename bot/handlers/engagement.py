from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select

from bot.keyboards.engagement import (
    challenge_kb,
    level_back_kb,
    stats_back_kb,
    tops_back_kb,
    tops_kb,
)
from bot.keyboards.main import main_menu_kb
from database.connection import async_session
from database.models import Profile, User, UserEngagement
from services.analytics.tracker import track
from services.engagement.archetypes import get_collection_stats
from services.engagement.challenges import get_user_challenge
from services.engagement.points import (
    MAX_LEVEL,
    POINTS,
    get_engagement,
    level_for_points,
    points_to_next_level,
    title_for_level,
)
from services.engagement.streaks import get_streak
from utils.logging import get_logger

router = Router()
logger = get_logger(__name__)


# ============================================================
# Утилиты
# ============================================================
async def _get_user_by_tg(telegram_id: int) -> User | None:
    async with async_session() as session:
        return (await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )).scalar_one_or_none()


def _progress_bar(current: int, target: int, width: int = 10) -> str:
    """Простой прогресс-бар из блоков."""
    if target <= 0:
        return "░" * width
    filled = min(width, int(current / target * width))
    return "█" * filled + "░" * (width - filled)


# ============================================================
# 🎯 ЧЕЛЛЕНДЖ ДНЯ
# ============================================================
@router.message(F.text == "🎯 Челлендж дня")
async def challenge_from_menu(message: Message):
    user = await _get_user_by_tg(message.from_user.id)
    if user is None:
        await message.answer("Сначала отправь фото!")
        return

    await _show_challenge(message, user.id)


@router.callback_query(F.data == "challenge_today")
async def challenge_from_callback(callback: CallbackQuery):
    await callback.answer()
    user = await _get_user_by_tg(callback.from_user.id)
    if user is None:
        await callback.message.answer("Сначала отправь фото!")
        return

    await _show_challenge(callback.message, user.id)


@router.callback_query(F.data == "challenge_noop")
async def challenge_noop(callback: CallbackQuery):
    await callback.answer("Выполняй задание из меню 👇", show_alert=True)


async def _show_challenge(message: Message, user_id: int):
    challenge = await get_user_challenge(user_id)

    if not challenge:
        await message.answer("Челлендж дня временно недоступен.")
        return

    progress = challenge.get("progress", 0)
    target = challenge.get("target_value", 1)
    status = challenge.get("status", "in_progress")

    if status == "completed":
        status_line = "✅ <b>Выполнено!</b>"
    else:
        status_line = (
            f"Прогресс: <b>{progress}/{target}</b>\n"
            f"{_progress_bar(progress, target)}"
        )

    text = (
        f"🎯 <b>ЧЕЛЛЕНДЖ ДНЯ</b>\n\n"
        f"<b>{challenge.get('title', '')}</b>\n\n"
        f"{challenge.get('description', '')}\n\n"
        f"{status_line}\n\n"
        f"🏆 Награда: <b>+{challenge.get('reward_points', 50)}</b> очков"
    )

    await message.answer(text, reply_markup=challenge_kb(challenge))

    await track("challenge_viewed", telegram_id=message.chat.id,
                payload={"challenge_id": challenge.get("challenge_id")})


# ============================================================
# 📊 МОЯ СТАТИСТИКА
# ============================================================
@router.message(F.text == "📊 Моя статистика")
async def stats_from_menu(message: Message):
    user = await _get_user_by_tg(message.from_user.id)
    if user is None:
        await message.answer("Сначала отправь фото!")
        return

    await _show_stats(message, user)


@router.callback_query(F.data == "my_stats")
async def stats_from_callback(callback: CallbackQuery):
    await callback.answer()
    user = await _get_user_by_tg(callback.from_user.id)
    if user is None:
        await callback.message.answer("Сначала отправь фото!")
        return

    await _show_stats(callback.message, user)


async def _show_stats(message: Message, user: User):
    # Engagement
    eng = await get_engagement(user.id)

    if eng is None:
        current_streak = 0
        total_points = 0
        level = 1
        max_streak = 0
        total_analyses = 0
        total_messages = 0
        total_tests = 0
        total_shares = 0
        total_referrals = 0
    else:
        current_streak = eng.current_streak
        total_points = eng.total_points
        level = eng.level
        max_streak = eng.max_streak
        total_analyses = eng.total_analyses
        total_messages = eng.total_messages
        total_tests = eng.total_tests
        total_shares = eng.total_shares
        total_referrals = eng.total_referrals

    # Коллекция архетипов
    collection = await get_collection_stats(user.id)

    title = title_for_level(level)
    to_next = points_to_next_level(total_points, level)

    # Прогресс до следующего уровня
    if level < MAX_LEVEL:
        # Находим очки текущего и следующего уровня
        from services.engagement.points import LEVELS
        current_threshold = 0
        next_threshold = 0
        for lvl, threshold, _ in LEVELS:
            if lvl == level:
                current_threshold = threshold
            if lvl == level + 1:
                next_threshold = threshold
                break
        level_progress = total_points - current_threshold
        level_total = next_threshold - current_threshold
        level_bar = _progress_bar(level_progress, level_total)
        level_line = (
            f"📈 Прогресс: {level_bar}\n"
            f"До уровня {level + 1}: <b>{to_next}</b> очков"
        )
    else:
        level_line = "🏆 <b>Максимальный уровень!</b>"

    text = (
        f"📊 <b>МОЯ СТАТИСТИКА</b>\n\n"
        f"🏅 Уровень: <b>{level}/{MAX_LEVEL}</b> — {title}\n"
        f"⭐ Очки: <b>{total_points}</b>\n"
        f"{level_line}\n\n"
        f"🔥 Стрик: <b>{current_streak}</b> дней\n"
        f"🏆 Рекорд стрика: <b>{max_streak}</b>\n\n"
        f"🎨 Архетипов: <b>{collection.get('unique', 0)}/{collection.get('max', 20)}</b>\n"
        f"📸 Анализов: <b>{total_analyses}</b>\n"
        f"💬 Сообщений: <b>{total_messages}</b>\n"
        f"🧪 Тестов: <b>{total_tests}</b>\n"
        f"📤 Шерингов: <b>{total_shares}</b>\n"
        f"👥 Приглашено друзей: <b>{total_referrals}</b>"
    )

    try:
        await message.answer(text, reply_markup=stats_back_kb())
    except Exception:
        logger.exception("Failed to send stats")


# ============================================================
# 🏅 УРОВЕНЬ (отдельный экран)
# ============================================================
@router.callback_query(F.data == "my_level")
async def level_from_callback(callback: CallbackQuery):
    await callback.answer()
    user = await _get_user_by_tg(callback.from_user.id)
    if user is None:
        await callback.message.answer("Сначала отправь фото!")
        return

    eng = await get_engagement(user.id)

    if eng is None:
        total_points = 0
        level = 1
    else:
        total_points = eng.total_points
        level = eng.level

    title = title_for_level(level)
    to_next = points_to_next_level(total_points, level)

    if level < MAX_LEVEL:
        from services.engagement.points import LEVELS
        current_threshold = 0
        next_threshold = 0
        for lvl, threshold, _ in LEVELS:
            if lvl == level:
                current_threshold = threshold
            if lvl == level + 1:
                next_threshold = threshold
                break
        level_progress = total_points - current_threshold
        level_total = next_threshold - current_threshold
        level_bar = _progress_bar(level_progress, level_total)
        progress_line = (
            f"{level_bar}\n"
            f"До уровня {level + 1}: <b>{to_next}</b> очков"
        )
    else:
        progress_line = "🏆 <b>Максимальный уровень достигнут!</b>"

    text = (
        f"🏅 <b>МОЙ УРОВЕНЬ</b>\n\n"
        f"Уровень: <b>{level}/{MAX_LEVEL}</b>\n"
        f"Титул: <b>{title}</b>\n"
        f"Очки: <b>{total_points}</b>\n\n"
        f"{progress_line}"
    )

    await callback.message.answer(text, reply_markup=level_back_kb())


# ============================================================
# 🏆 ТОПЫ
# ============================================================
@router.message(F.text == "🏆 Топы")
async def tops_from_menu(message: Message):
    await message.answer(
        "🏆 <b>ТОПЫ</b>\n\n"
        "Выбери категорию:",
        reply_markup=tops_kb(),
    )


@router.callback_query(F.data == "tops_menu")
async def tops_from_callback(callback: CallbackQuery):
    await callback.answer()
    await callback.message.answer(
        "🏆 <b>ТОПЫ</b>\n\n"
        "Выбери категорию:",
        reply_markup=tops_kb(),
    )


@router.callback_query(F.data.startswith("top_"))
async def top_show(callback: CallbackQuery):
    await callback.answer("Считаю...")
    category = callback.data.replace("top_", "")

    text = await _build_top(category)

    try:
        await callback.message.edit_text(text, reply_markup=tops_back_kb())
    except Exception:
        await callback.message.answer(text, reply_markup=tops_back_kb())


async def _build_top(category: str) -> str:
    """Строит текст топа по категории."""
    from database.models import UserAchievement  # noqa

    header_map = {
        "chaos": "🔥 ТОП-10 ПО ХАОСУ",
        "humor": "😂 ТОП-10 ПО ЮМОРУ",
        "charisma": "✨ ТОП-10 ПО ХАРИЗМЕ",
        "points": "🏆 ТОП-10 ПО ОЧКАМ",
        "referrals": "👥 ТОП-5 ПО ДРУЗЬЯМ",
    }
    header = header_map.get(category, "🏆 ТОП")

    async with async_session() as session:
        if category in ("chaos", "humor", "charisma"):
            # Из profiles
            column = {
                "chaos": Profile.chaos,
                "humor": Profile.humor,
                "charisma": Profile.charisma,
            }[category]

            rows = (await session.execute(
                select(Profile, User)
                .join(User, User.id == Profile.user_id)
                .where(User.is_blocked.is_(False))
                .where(User.participates_in_game.is_(True))
                .order_by(column.desc())
                .limit(10)
            )).all()

            lines = [f"{header}\n"]
            for i, (p, u) in enumerate(rows, 1):
                score = getattr(p, category)
                name = u.first_name or "Игрок"
                if u.show_username and u.username:
                    name += f" @{u.username}"
                lines.append(f"{i}. <b>{name}</b> — {score}")

        elif category == "points":
            rows = (await session.execute(
                select(UserEngagement, User)
                .join(User, User.id == UserEngagement.user_id)
                .where(User.is_blocked.is_(False))
                .order_by(UserEngagement.total_points.desc())
                .limit(10)
            )).all()

            lines = [f"{header}\n"]
            for i, (e, u) in enumerate(rows, 1):
                name = u.first_name or "Игрок"
                if u.show_username and u.username:
                    name += f" @{u.username}"
                title = title_for_level(e.level)
                lines.append(f"{i}. <b>{name}</b> — {e.total_points} (ур. {e.level}, {title})")

        elif category == "referrals":
            rows = (await session.execute(
                select(UserEngagement, User)
                .join(User, User.id == UserEngagement.user_id)
                .where(User.is_blocked.is_(False))
                .where(UserEngagement.total_referrals > 0)
                .order_by(UserEngagement.total_referrals.desc())
                .limit(5)
            )).all()

            lines = [f"{header}\n"]
            for i, (e, u) in enumerate(rows, 1):
                name = u.first_name or "Игрок"
                lines.append(f"{i}. <b>{name}</b> — {e.total_referrals} друзей")

        else:
            return "Неизвестная категория."

    if len(lines) == 1:
        lines.append("<i>Пока пусто. Стань первым!</i>")

    return "\n".join(lines)


@router.callback_query(F.data == "noop")
async def noop(callback: CallbackQuery):
    await callback.answer()