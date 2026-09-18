from typing import Dict

from aiogram import F, Router
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy import delete, or_, select

from bot.keyboards.matching import match_actions_kb, modes_kb
from config import config
from database.connection import async_session
from database.models import Match, User
from services.access import has_full_access
from services.achievements import unlock_achievement
from services.ai.factory import get_ai_provider
from services.analytics.tracker import track
from services.matching.matcher import (
    create_match_record,
    find_candidates,
    get_my_profile,
    get_my_user,
)
from utils.logging import get_logger

router = Router()
logger = get_logger(__name__)

# Память показанных кандидатов: telegram_id → {"mode":..., "shown_ids":[...]}
SEARCH_STATE: Dict[int, dict] = {}

PREMIUM_MODES = {"intellectual", "chaos"}


# ============================================================
# Хелперы
# ============================================================
def _candidate_text(c: dict) -> str:
    p = c["profile"]
    username_str = f"@{c['username']}" if (c["username"] and c["show_username"]) else "Скрыт"
    name = c["first_name"] or "Игрок"
    return (
        f"🎯 Совпадение: <b>{c['score']}%</b>\n"
        f"👤 {name}\n"
        f"🧨 {p['archetype']}\n"
        f"Харизма {p['charisma']} · Юмор {p['humor']} · Хаос {p['chaos']}\n"
        f"Username: {username_str}"
    )


def _empty_candidates_kb(mode: str) -> InlineKeyboardMarkup:
    """Кнопки, если больше нет кандидатов."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="🔄 Показать заново",
                callback_data=f"restart_mode_{mode}",
            )],
            [InlineKeyboardButton(
                text="🎛 Сменить режим",
                callback_data="find_players",
            )],
        ]
    )


async def _send_next_candidate(callback: CallbackQuery, mode: str, telegram_id: int) -> None:
    async with async_session() as session:
        me = await get_my_user(session, telegram_id)
        if me is None:
            await callback.message.answer("Сначала отправь фото!")
            return

        state = SEARCH_STATE.setdefault(telegram_id, {"mode": mode, "shown_ids": []})

        # Админ, whitelist и PRO получают расширенный лимит
        full = await has_full_access(telegram_id)
        limit = 50 if full else 20

        candidates = await find_candidates(
            session,
            me.id,
            mode=mode,
            limit=limit,
            exclude_ids=set(state["shown_ids"]),
        )

    if not candidates:
        shown_count = len(state.get("shown_ids", []))
        if shown_count == 0:
            await callback.message.answer(
                "😔 Пока нет подходящих игроков.\n\n"
                "Пригласи друзей через «📤 Поделиться» или загляни позже!",
                reply_markup=_empty_candidates_kb(mode),
            )
        else:
            await callback.message.answer(
                f"🎯 Ты уже посмотрел всех игроков в этом режиме ({shown_count}).\n\n"
                f"Хочешь пройтись по ним заново?",
                reply_markup=_empty_candidates_kb(mode),
            )
        return

    c = candidates[0]
    state["shown_ids"].append(c["user_id"])
    state["mode"] = mode

    # Сохраняем запись о матче в БД
    async with async_session() as session:
        me = await get_my_user(session, telegram_id)
        await create_match_record(session, me.id, c["user_id"], mode, c["score"])

    await track(
        "match_created",
        telegram_id=telegram_id,
        payload={"mode": mode, "score": c["score"]},
    )
    await unlock_achievement(me.id, "first_match")

    # AI-описание матча
    description_line = ""
    try:
        async with async_session() as session:
            me = await get_my_user(session, telegram_id)
            my_p = await get_my_profile(session, me.id)
            my_dict = {
                "archetype": my_p.archetype if my_p else "",
                "charisma": my_p.charisma if my_p else 0,
                "humor": my_p.humor if my_p else 0,
                "energy": my_p.energy if my_p else 0,
                "chaos": my_p.chaos if my_p else 0,
                "intellect": my_p.intellect if my_p else 0,
            }
        ai = await get_ai_provider().generate_match_description(
            my_dict, c["profile"], c["score"]
        )
        description_line = (
            f"\n\n<i>{ai.get('headline', '')}</i>\n"
            f"{ai.get('description', '')}\n"
            f"😂 {ai.get('chaos_comment', '')}"
        )
    except Exception:
        logger.exception("Match description AI failed")

    text = _candidate_text(c) + description_line
    await callback.message.answer(text, reply_markup=match_actions_kb(c["user_id"], c["score"]))


# ============================================================
# REPLY-КНОПКА «🎯 Найти игроков»
# ============================================================
@router.message(F.text == "🎯 Найти игроков")
async def find_players(message: Message):
    if not config.MATCHING_ENABLED:
        await message.answer("Поиск игроков временно отключён.")
        return
    await message.answer("Выбери режим поиска:", reply_markup=modes_kb())


# ============================================================
# CALLBACK: ВЫБОР РЕЖИМА
# ============================================================
@router.callback_query(F.data.startswith("mode_"))
async def mode_selected(callback: CallbackQuery):
    await callback.answer()
    if not config.MATCHING_ENABLED:
        await callback.message.answer("Поиск игроков отключён.")
        return

    mode = callback.data.replace("mode_", "")

    # PRO-режимы: доступны админам, whitelist и PRO
    if mode in PREMIUM_MODES:
        if not await has_full_access(callback.from_user.id):
            await callback.message.answer(
                "💎 Этот режим доступен только с PRO.\n\n"
                "Оформить: /start → 💎 PRO"
            )
            return

    await track("search_used", telegram_id=callback.from_user.id, payload={"mode": mode})

    # Сбрасываем shown_ids — начинаем с чистого листа
    SEARCH_STATE[callback.from_user.id] = {"mode": mode, "shown_ids": []}

    # Чистим старые незавершённые matches, чтобы find_candidates
    # не отсеивал игроков, которых мы уже показывали и не взаимодействовали
    await _clear_fresh_matches(callback.from_user.id)

    await _send_next_candidate(callback, mode, callback.from_user.id)


# ============================================================
# CALLBACK: СЛЕДУЮЩИЙ КАНДИДАТ
# ============================================================
@router.callback_query(F.data == "next_candidate")
async def next_candidate(callback: CallbackQuery):
    await callback.answer("Ищу следующего...")
    state = SEARCH_STATE.get(callback.from_user.id)
    mode = state["mode"] if state else "similar"
    await _send_next_candidate(callback, mode, callback.from_user.id)


# ============================================================
# CALLBACK: ПОКАЗАТЬ ЗАНОВО
# ============================================================
@router.callback_query(F.data.startswith("restart_mode_"))
async def restart_mode(callback: CallbackQuery):
    """
    Полный сброс поиска:
    - чистим shown_ids в памяти,
    - удаляем matches со статусом 'new' между мной и остальными,
    - запускаем поиск заново.

    Статусы 'blocked', 'matched', 'chatted' НЕ трогаем —
    они остаются, и такие игроки не появятся снова.
    """
    await callback.answer("Показываю заново...")
    mode = callback.data.replace("restart_mode_", "")

    SEARCH_STATE[callback.from_user.id] = {"mode": mode, "shown_ids": []}

    await _clear_fresh_matches(callback.from_user.id)

    await _send_next_candidate(callback, mode, callback.from_user.id)


# ============================================================
# Хелпер: удаляем только "свежие" matches (status='new')
# ============================================================
async def _clear_fresh_matches(telegram_id: int) -> None:
    """
    Удаляет matches между пользователем и остальными,
    но только те, что в статусе 'new'.

    Не трогает:
    - status='blocked' — заблокированные
    - status='matched' — взаимные
    - status='chatted' — уже общались

    Это позволяет:
    - "Показать заново" видеть тех, с кем не взаимодействовал;
    - сохранять блокировки и историю диалогов.
    """
    try:
        async with async_session() as session:
            me = (await session.execute(
                select(User).where(User.telegram_id == telegram_id)
            )).scalar_one_or_none()

            if me is None:
                return

            result = await session.execute(
                delete(Match).where(
                    or_(Match.user1_id == me.id, Match.user2_id == me.id),
                    Match.status == "new",
                )
            )
            await session.commit()
            logger.info(f"[SEARCH] Cleared {result.rowcount} 'new' matches for user {me.id}")
    except Exception:
        logger.exception("Failed to clear 'new' matches")


# ============================================================
# CALLBACK: МЕНЮ РЕЖИМОВ
# ============================================================
@router.callback_query(F.data == "find_players")
async def cb_find_players(callback: CallbackQuery):
    await callback.answer()
    await callback.message.answer("Выбери режим поиска:", reply_markup=modes_kb())