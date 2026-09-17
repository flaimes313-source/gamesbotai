from typing import Dict

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from bot.keyboards.matching import match_actions_kb, modes_kb
from config import config
from database.connection import async_session
from services.achievements import unlock_achievement
from services.ai.factory import get_ai_provider
from services.analytics.tracker import track
from services.matching.matcher import (
    create_match_record,
    find_candidates,
    get_my_profile,
    get_my_user,
)
from services.premium import is_premium
from utils.logging import get_logger

router = Router()
logger = get_logger(__name__)

SEARCH_STATE: Dict[int, dict] = {}

PREMIUM_MODES = {"intellectual", "chaos"}


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


async def _send_next_candidate(callback: CallbackQuery, mode: str, telegram_id: int) -> None:
    async with async_session() as session:
        me = await get_my_user(session, telegram_id)
        if me is None:
            await callback.message.answer("Сначала отправь фото!")
            return

        state = SEARCH_STATE.setdefault(telegram_id, {"mode": mode, "shown_ids": []})

        limit = 50 if await is_premium(telegram_id) else 20
        candidates = await find_candidates(
            session,
            me.id,
            mode=mode,
            limit=limit,
            exclude_ids=set(state["shown_ids"]),
        )

    if not candidates:
        await callback.message.answer(
            "😔 Больше нет подходящих игроков. Попробуй другой режим или загляни позже!"
        )
        return

    c = candidates[0]
    state["shown_ids"].append(c["user_id"])
    state["mode"] = mode

    async with async_session() as session:
        me = await get_my_user(session, telegram_id)
        await create_match_record(session, me.id, c["user_id"], mode, c["score"])

    await track(
        "match_created",
        telegram_id=telegram_id,
        payload={"mode": mode, "score": c["score"]},
    )
    await unlock_achievement(me.id, "first_match")

    # AI-описание
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


@router.message(F.text == "🎯 Найти игроков")
async def find_players(message: Message):
    if not config.MATCHING_ENABLED:
        await message.answer("Поиск игроков временно отключён.")
        return
    await message.answer("Выбери режим поиска:", reply_markup=modes_kb())


@router.callback_query(F.data.startswith("mode_"))
async def mode_selected(callback: CallbackQuery):
    await callback.answer()
    if not config.MATCHING_ENABLED:
        await callback.message.answer("Поиск игроков отключён.")
        return

    mode = callback.data.replace("mode_", "")

    if mode in PREMIUM_MODES:
        if not await is_premium(callback.from_user.id):
            await callback.message.answer(
                "💎 Этот режим доступен только с PRO.\n"
                "Оформить: /start → 💎 PRO"
            )
            return

    await track("search_used", telegram_id=callback.from_user.id, payload={"mode": mode})
    SEARCH_STATE[callback.from_user.id] = {"mode": mode, "shown_ids": []}
    await _send_next_candidate(callback, mode, callback.from_user.id)


@router.callback_query(F.data == "next_candidate")
async def next_candidate(callback: CallbackQuery):
    await callback.answer("Ищу следующего...")
    state = SEARCH_STATE.get(callback.from_user.id)
    mode = state["mode"] if state else "similar"
    await _send_next_candidate(callback, mode, callback.from_user.id)


@router.callback_query(F.data == "find_players")
async def cb_find_players(callback: CallbackQuery):
    await callback.answer()
    await callback.message.answer("Выбери режим поиска:", reply_markup=modes_kb())