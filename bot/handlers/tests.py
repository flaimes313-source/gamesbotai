from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select

from database.connection import async_session
from database.models import Test, User, UserTest
from services.ai.factory import get_ai_provider
from utils.logging import get_logger

router = Router()
logger = get_logger(__name__)

# Кэш состояния прохождения тестов: telegram_id -> {"test_id":..., "question":..., "answers":[...]}
ACTIVE_TESTS: dict[int, dict] = {}


async def _tests_menu_kb() -> InlineKeyboardMarkup:
    async with async_session() as session:
        tests = (await session.execute(select(Test).where(Test.is_active.is_(True)).order_by(Test.sort_order))).scalars().all()

    rows = [[InlineKeyboardButton(text=f"🧪 {t.name}", callback_data=f"test_start_{t.id}")] for t in tests]
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data == "tests_menu")
async def cb_tests_menu(callback: CallbackQuery):
    await callback.answer()
    await callback.message.answer("🧪 Выбери тест:", reply_markup=await _tests_menu_kb())


@router.callback_query(F.data.startswith("test_start_"))
async def cb_test_start(callback: CallbackQuery):
    await callback.answer()
    test_id = int(callback.data.replace("test_start_", ""))

    async with async_session() as session:
        test = (await session.execute(select(Test).where(Test.id == test_id))).scalar_one_or_none()

    if test is None:
        await callback.message.answer("Тест не найден.")
        return

    await callback.message.answer(f"🧪 Загружаю тест «{test.name}»...")

    try:
        question = await get_ai_provider().generate_test_question(test.name, test.description or "")
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

    await _send_question(callback, question)


async def _send_question(callback: CallbackQuery, question: dict):
    options = question.get("options", [])
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=opt[:60], callback_data=f"test_answer_{i}")]
            for i, opt in enumerate(options)
        ]
    )
    await callback.message.answer(
        f"❓ {question.get('question', '')}",
        reply_markup=kb,
    )


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

    # Ограничимся 5 вопросами
    if state["question_index"] < 5:
        try:
            q = await get_ai_provider().generate_test_question(state["test_name"], "")
            state["questions"].append(q)
        except Exception:
            logger.exception("Next question failed")
        await _send_question(callback, state["questions"][state["question_index"]])
        return

    # Завершаем тест
    await _finalize_test(callback, state)


async def _finalize_test(callback: CallbackQuery, state: dict):
    await callback.message.answer("🔎 Считаю результат...")

    try:
        result = await get_ai_provider().generate_test_result(state["test_name"], state["answers"])
    except Exception:
        logger.exception("Test result failed")
        result = {"title": "ТЕСТ ПРОЙДЕН", "text": "Результат недоступен.", "emoji": "🧪"}

    # Сохраняем
    async with async_session() as session:
        user = (await session.execute(select(User).where(User.telegram_id == callback.from_user.id))).scalar_one_or_none()
        if user:
            session.add(UserTest(user_id=user.id, test_id=state["test_id"], result_json=result))
            await session.commit()

    await callback.message.answer(
        f"{result.get('emoji', '🧪')} <b>{result.get('title', '')}</b>\n\n{result.get('text', '')}"
    )

    ACTIVE_TESTS.pop(callback.from_user.id, None)