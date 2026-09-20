from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import func, select

from database.connection import async_session
from database.models import Test, User, UserTest
from services.access import has_full_access
from services.achievements import unlock_achievement
from services.ai.factory import get_ai_provider
from services.analytics.tracker import track
from utils.logging import get_logger

router = Router()
logger = get_logger(__name__)

ACTIVE_TESTS: dict[int, dict] = {}
TOTAL_QUESTIONS = 5


async def _tests_menu_kb(telegram_id: int) -> InlineKeyboardMarkup:
    full = await has_full_access(telegram_id)

    async with async_session() as session:
        tests = (await session.execute(
            select(Test).where(Test.is_active.is_(True)).order_by(Test.sort_order)
        )).scalars().all()

    rows = []
    for t in tests:
        if t.is_premium and not full:
            rows.append([InlineKeyboardButton(
                text=f"💎 {t.name}",
                callback_data=f"test_locked_{t.id}",
            )])
        else:
            emoji = "🧪" if not t.is_premium else "💎🧪"
            rows.append([InlineKeyboardButton(
                text=f"{emoji} {t.name}",
                callback_data=f"test_start_{t.id}",
            )])

    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data == "tests_menu")
async def cb_tests_menu(callback: CallbackQuery):
    await callback.answer()
    await callback.message.answer(
        "🧪 Выбери тест:",
        reply_markup=await _tests_menu_kb(callback.from_user.id),
    )


@router.callback_query(F.data.startswith("test_locked_"))
async def cb_test_locked(callback: CallbackQuery):
    await callback.answer()
    await callback.message.answer(
        "💎 <b>Этот тест доступен только с PRO</b>\n\n"
        "С PRO ты получаешь доступ ко всем тестам.\n\n"
        "Оформить: /start → 💎 PRO"
    )


async def _send_question(callback: CallbackQuery, question: dict):
    options = question.get("options", [])
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=opt[:60], callback_data=f"test_answer_{i}")]
            for i, opt in enumerate(options)
        ]
    )

    state = ACTIVE_TESTS.get(callback.from_user.id, {})
    idx = state.get("question_index", 0) + 1
    total = TOTAL_QUESTIONS
    progress = "█" * idx + "░" * (total - idx)

    await callback.message.answer(
        f"<b>Вопрос {idx}/{total}</b>  {progress}\n\n"
        f"❓ {question.get('question', '')}",
        reply_markup=kb,
    )


@router.callback_query(F.data.startswith("test_start_"))
async def cb_test_start(callback: CallbackQuery):
    await callback.answer()
    test_id = int(callback.data.replace("test_start_", ""))

    async with async_session() as session:
        test = (await session.execute(select(Test).where(Test.id == test_id))).scalar_one_or_none()

    if test is None:
        await callback.message.answer("Тест не найден.")
        return

    if test.is_premium and not await has_full_access(callback.from_user.id):
        await callback.message.answer("💎 Этот тест доступен только с PRO.")
        return

    await callback.message.answer(f"🧪 Загружаю тест «{test.name}»...")

    try:
        provider = await get_ai_provider()
        question = await provider.generate_test_question(test.name, test.description or "")
    except Exception:
        logger.exception("Test question generation failed")
        await callback.message.answer("😔 AI сейчас недоступен. Попробуй позже.")
        return

    ACTIVE_TESTS[callback.from_user.id] = {
        "test_id": test.id,
        "test_name": test.name,
        "question_index": 0,
        "questions": [question],
        "answers": [],
    }

    await track("test_started", telegram_id=callback.from_user.id, payload={"test_id": test_id})
    await _send_question(callback, question)


@router.callback_query(F.data.startswith("test_answer_"))
async def cb_test_answer(callback: CallbackQuery):
    await callback.answer()
    state = ACTIVE_TESTS.get(callback.from_user.id)
    if not state:
        await callback.message.answer("Начни тест заново через меню.")
        return

    idx = int(callback.data.replace("test_answer_", ""))
    current_q = state["questions"][state["question_index"]]
    options = current_q.get("options", [])
    if idx >= len(options):
        await callback.message.answer("Некорректный ответ.")
        return

    state["answers"].append(options[idx])
    state["question_index"] += 1

    if state["question_index"] < TOTAL_QUESTIONS:
        try:
            provider = await get_ai_provider()
            q = await provider.generate_test_question(state["test_name"], "")
            state["questions"].append(q)
        except Exception:
            logger.exception("Next question failed")
        await _send_question(callback, state["questions"][state["question_index"]])
        return

    await _finalize_test(callback, state)


async def _finalize_test(callback: CallbackQuery, state: dict):
    await callback.message.answer("🔎 Считаю результат...")

    try:
        provider = await get_ai_provider()
        result = await provider.generate_test_result(state["test_name"], state["answers"])
    except Exception:
        logger.exception("Test result failed")
        result = {"title": "ТЕСТ ПРОЙДЕН", "text": "Результат недоступен.", "emoji": "🧪"}

    async with async_session() as session:
        user = (await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )).scalar_one_or_none()

        if user:
            session.add(UserTest(user_id=user.id, test_id=state["test_id"], result_json=result))
            await session.commit()

            await unlock_achievement(user.id, "first_test")

            cnt = (await session.execute(
                select(func.count(UserTest.id)).where(UserTest.user_id == user.id)
            )).scalar_one()
            if cnt >= 5:
                await unlock_achievement(user.id, "five_tests")

    # Вовлечение: тест + челлендж
    if user:
        try:
            from services.engagement.service import on_test_completed
            challenge_result = await on_test_completed(user.id)

            if challenge_result.get("completed"):
                await callback.message.answer(
                    "🎯 <b>Челлендж дня выполнен!</b>\n\n"
                    f"Награда: +{challenge_result.get('reward_points', 50)} очков"
                )
        except Exception:
            logger.exception("Engagement on_test_completed failed")

    await track("test_completed", telegram_id=callback.from_user.id, payload={"test_id": state["test_id"]})

    await callback.message.answer(
        f"{result.get('emoji', '🧪')} <b>{result.get('title', '')}</b>\n\n{result.get('text', '')}"
    )

    ACTIVE_TESTS.pop(callback.from_user.id, None)