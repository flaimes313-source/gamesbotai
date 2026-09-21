from aiogram import F, Router
from aiogram.types import BufferedInputFile, CallbackQuery, Message
from sqlalchemy import select

from bot.keyboards.main import main_menu_kb, share_link_kb, settings_kb
from bot.keyboards.profile import profile_kb
from database.connection import async_session
from database.models import Profile, User
from services.analytics.tracker import track
from services.analysis.dynamics import (
    build_progress_bar,
    format_delta,
    format_period,
    get_biggest_changes,
    get_dynamics,
    get_other_changes,
)
from services.cards.dynamics_chart import generate_dynamics_chart
from services.engagement.points import (
    MAX_LEVEL,
    get_engagement,
    points_to_next_level,
    title_for_level,
)
from utils.logging import get_logger

router = Router()
logger = get_logger(__name__)


# ============================================================
# Хелперы
# ============================================================
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


def _profile_text(user: User, profile: Profile, engagement_line: str = "") -> str:
    base = (
        f"👤 <b>МОЙ ПРОФИЛЬ</b>\n\n"
        f"🧨 <b>{profile.archetype}</b>\n\n"
        f"Харизма {profile.charisma}\n"
        f"Уверенность {profile.confidence}\n"
        f"Юмор {profile.humor}\n"
        f"Энергия {profile.energy}\n"
        f"Интеллект {profile.intellect}\n"
        f"Креативность {profile.creativity}\n"
        f"Хаос {profile.chaos}\n\n"
        f"⚠️ Опасность для друзей: {profile.danger_level}\n"
    )
    if engagement_line:
        base += f"\n{engagement_line}"
    if profile.vibe:
        base += f"\n\n<i>{profile.vibe}</i>"
    return base


async def _send_share_link(bot, telegram_id: int, message_or_callback) -> None:
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
    await track("share_generated", telegram_id=telegram_id)

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
# REPLY-КНОПКИ
# ============================================================
@router.message(F.text == "👤 Мой профиль")
async def show_profile(message: Message):
    user, profile = await _latest_profile(message.from_user.id)
    if profile is None or user is None:
        await message.answer(
            "У тебя пока нет профиля. Отправь фото 📸 чтобы пройти первый анализ!"
        )
        return

    # Engagement
    engagement_line = ""
    try:
        eng = await get_engagement(user.id)
        if eng:
            title = title_for_level(eng.level)
            to_next = points_to_next_level(eng.total_points, eng.level)

            engagement_line = (
                f"🏅 Уровень: <b>{eng.level}/{MAX_LEVEL}</b> — {title}\n"
                f"⭐ Очки: <b>{eng.total_points}</b>\n"
            )
            if eng.current_streak > 0:
                engagement_line += f"🔥 Стрик: <b>{eng.current_streak}</b> дней\n"
            if to_next > 0 and eng.level < MAX_LEVEL:
                engagement_line += f"📈 До следующего: <b>{to_next}</b> очков"
    except Exception:
        logger.exception("Engagement fetch failed")

    await message.answer(
        _profile_text(user, profile, engagement_line),
        reply_markup=profile_kb(),
    )


@router.message(F.text == "📤 Поделиться")
async def share_from_menu(message: Message):
    await _send_share_link(message.bot, message.from_user.id, message)


@router.message(F.text == "⚙️ Настройки")
async def settings_from_menu(message: Message):
    await message.answer(
        "⚙️ <b>Настройки</b>\n\nЧто хочешь настроить?",
        reply_markup=settings_kb(),
    )


# ============================================================
# 📈 МОЯ ДИНАМИКА
# ============================================================
@router.callback_query(F.data == "my_dynamics")
async def cb_my_dynamics(callback: CallbackQuery):
    await callback.answer()

    async with async_session() as session:
        user = (await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )).scalar_one_or_none()

    if user is None:
        await callback.message.answer("Сначала отправь фото — появятся данные для динамики!")
        return

    try:
        dyn = await get_dynamics(user.id, limit=10)
    except Exception:
        logger.exception("[DYNAMICS] get_dynamics failed")
        await callback.message.answer("😔 Не удалось собрать динамику. Попробуй позже.")
        return

    if not dyn.get("has_enough_data"):
        await callback.message.answer(
            "📈 <b>Моя динамика</b>\n\n"
            "У тебя пока <b>меньше 2 анализов</b>.\n\n"
            "Сделай ещё один анализ — и я покажу, "
            "как меняется твой вайб со временем! 🔥"
        )
        return

    text = _render_dynamics_text(dyn)

    try:
        await track(
            "dynamics_viewed",
            telegram_id=callback.from_user.id,
            payload={"count": dyn.get("count", 0)},
        )
    except Exception:
        logger.exception("[DYNAMICS] track failed")

    await callback.message.answer(text)

    # === График ===
    try:
        await _send_dynamics_chart(callback, dyn)
    except Exception:
        logger.exception("[DYNAMICS] chart failed")


async def _send_dynamics_chart(callback: CallbackQuery, dyn: dict):
    """Рисует и отправляет график по характеристике с наибольшим изменением."""
    top = get_biggest_changes(dyn, top=1)
    if not top:
        return

    field_key, field_data = top[0]
    history = field_data.get("history") or []
    label = field_data.get("label") or field_key

    period = dyn.get("period") or {}
    period_str = format_period(period.get("first"), period.get("last"))

    # Последний архетип (для выбора темы)
    archetypes = dyn.get("archetypes") or []
    archetype = archetypes[-1] if archetypes else None

    bot_username = (await callback.bot.get_me()).username

    png_bytes = generate_dynamics_chart(
        history=history,
        label=label,
        period=period_str,
        archetype=archetype,
        bot_username=bot_username,
    )

    photo = BufferedInputFile(png_bytes, filename="dynamics.png")
    await callback.message.answer_photo(photo)


def _render_dynamics_text(dyn: dict) -> str:
    """Собирает текст экрана динамики."""
    count = dyn.get("count", 0)
    period = dyn.get("period") or {}
    period_str = format_period(period.get("first"), period.get("last"))

    top = get_biggest_changes(dyn, top=2)
    top_keys = [k for k, _ in top]
    others = get_other_changes(dyn, exclude=top_keys)

    lines = [
        "📈 <b>МОЯ ДИНАМИКА</b>",
        "",
        f"📊 Анализов: <b>{count}</b>",
    ]
    if period_str:
        lines.append(f"📅 {period_str}")
    lines.append("")
    lines.append("━" * 15)
    lines.append("")

    # Топ-2 с прогресс-барами
    for field_key, data in top:
        label = data.get("label", field_key)
        first_val = data.get("first", 0)
        last_val = data.get("last", 0)
        delta = data.get("delta", 0)
        bar = build_progress_bar(last_val)

        lines.append(f"<b>{label}</b>")
        lines.append(f"{first_val} → {last_val}   <b>{format_delta(delta)}</b>")
        lines.append(f"<code>{bar}</code>")
        lines.append("")

    # Остальные — компактно
    if others:
        lines.append("━" * 15)
        lines.append("")
        for field_key, data in others:
            label = data.get("label", field_key)
            first_val = data.get("first", 0)
            last_val = data.get("last", 0)
            delta = data.get("delta", 0)
            lines.append(
                f"{label}  {first_val} → {last_val}  "
                f"<b>{format_delta(delta)}</b>"
            )

    return "\n".join(lines)


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
    text = "⚙️ <b>Настройки</b>\n\nЧто хочешь настроить?"
    try:
        await callback.message.edit_text(text, reply_markup=settings_kb())
    except Exception:
        await callback.message.answer(text, reply_markup=settings_kb())


@router.callback_query(F.data == "back_to_main")
async def cb_back_to_main(callback: CallbackQuery):
    await callback.answer()
    try:
        await callback.message.edit_text(
            "🏠 <b>Главное меню</b>",
            reply_markup=None,
        )
    except Exception:
        pass
    await callback.message.answer(
        "🏠 Главное меню. Отправь фото или выбери пункт меню.",
        reply_markup=main_menu_kb(),
    )