"""
Квесты — цепочки заданий.

Логика:
- При первом действии юзера (любого) автостартует первый квест
  по sort_order, у которого ещё нет записи в UserQuestProgress.
- После завершения квеста — при следующем действии автостартует
  следующий незапущенный квест.
- advance_quest продвигает ОДИН активный квест за вызов
  (первый по sort_order, у которого текущий шаг совпадает
  с task_type действия).
"""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select

from database.connection import async_session
from database.models import Quest, QuestStep, UserQuestProgress
from services.engagement.points import add_custom_points
from utils.logging import get_logger

logger = get_logger(__name__)


# ============================================================
# РЕЕСТР КВЕСТОВ
# ============================================================
QUESTS_SEED = [
    {
        "code": "explorer",
        "title": "Исследователь",
        "description": "Пройди базовый путь в Вайбми",
        "emoji": "🧭",
        "sort_order": 1,
        "steps": [
            {"title": "Первый шаг", "description": "Отправь фото на анализ", "task_type": "photo", "target_value": 1, "reward_points": 50},
            {"title": "Познакомься", "description": "Найди игрока", "task_type": "search", "target_value": 1, "reward_points": 50},
            {"title": "Узнай себя", "description": "Пройди тест", "task_type": "test", "target_value": 1, "reward_points": 100},
            {"title": "Поделись", "description": "Поделись карточкой", "task_type": "share", "target_value": 1, "reward_points": 150},
        ],
    },
    {
        "code": "communicator",
        "title": "Коммуникатор",
        "description": "Научись общаться в Вайбми",
        "emoji": "💬",
        "sort_order": 2,
        "steps": [
            {"title": "Первое слово", "description": "Отправь сообщение игроку", "task_type": "message", "target_value": 1, "reward_points": 50},
            {"title": "Болтун", "description": "Отправь 5 сообщений", "task_type": "message", "target_value": 5, "reward_points": 150},
            {"title": "Сравнись", "description": "Сравни профиль с игроком", "task_type": "compare", "target_value": 1, "reward_points": 100},
            {"title": "Приведи друга", "description": "Пригласи друга в бот", "task_type": "invite", "target_value": 1, "reward_points": 200},
        ],
    },
]


# ============================================================
# SEED
# ============================================================
async def seed_quests() -> None:
    """Создаёт квесты и шаги, если их нет."""
    async with async_session() as session:
        for q in QUESTS_SEED:
            existing = (await session.execute(
                select(Quest).where(Quest.code == q["code"])
            )).scalar_one_or_none()

            if existing:
                continue

            quest = Quest(
                code=q["code"],
                title=q["title"],
                description=q["description"],
                emoji=q["emoji"],
                sort_order=q["sort_order"],
            )
            session.add(quest)
            await session.flush()

            for i, step in enumerate(q["steps"], 1):
                session.add(QuestStep(
                    quest_id=quest.id,
                    step_number=i,
                    title=step["title"],
                    description=step["description"],
                    task_type=step["task_type"],
                    target_value=step["target_value"],
                    reward_points=step["reward_points"],
                ))

        await session.commit()
    logger.info("[QUESTS] Seeded")


# ============================================================
# ЧТЕНИЕ
# ============================================================
async def get_active_quests(user_id: int) -> list:
    """Все активные квесты + прогресс юзера."""
    async with async_session() as session:
        quests = (await session.execute(
            select(Quest).where(Quest.is_active.is_(True)).order_by(Quest.sort_order)
        )).scalars().all()

        result = []
        for q in quests:
            prog = (await session.execute(
                select(UserQuestProgress).where(
                    UserQuestProgress.user_id == user_id,
                    UserQuestProgress.quest_id == q.id,
                )
            )).scalar_one_or_none()

            total_steps = (await session.execute(
                select(QuestStep).where(QuestStep.quest_id == q.id)
            )).scalars().all()

            result.append({
                "quest_id": q.id,
                "code": q.code,
                "title": q.title,
                "description": q.description,
                "emoji": q.emoji,
                "total_steps": len(total_steps),
                "current_step": prog.current_step if prog else 1,
                "status": prog.status if prog else "not_started",
            })

        return result


async def get_quest_step(quest_id: int, step_number: int) -> Optional[QuestStep]:
    async with async_session() as session:
        return (await session.execute(
            select(QuestStep).where(
                QuestStep.quest_id == quest_id,
                QuestStep.step_number == step_number,
            )
        )).scalar_one_or_none()


# ============================================================
# СТАРТ КВЕСТА (явный)
# ============================================================
async def start_quest(user_id: int, quest_id: int) -> bool:
    """Начать квест вручную. Возвращает False, если уже начат."""
    async with async_session() as session:
        existing = (await session.execute(
            select(UserQuestProgress).where(
                UserQuestProgress.user_id == user_id,
                UserQuestProgress.quest_id == quest_id,
            )
        )).scalar_one_or_none()

        if existing:
            return False

        session.add(UserQuestProgress(
            user_id=user_id,
            quest_id=quest_id,
            current_step=1,
            step_progress=0,
            status="in_progress",
        ))
        await session.commit()

    return True


# ============================================================
# ПРОДВИЖЕНИЕ
# ============================================================
async def advance_quest(user_id: int, task_type: str, amount: int = 1) -> dict:
    """
    Продвигает ОДИН активный квест юзера (первый по sort_order),
    у которого текущий шаг совпадает с task_type.

    Если у юзера нет ни одного активного квеста — автостартует
    первый по sort_order, у которого ещё нет записи в UserQuestProgress.

    Если все квесты завершены и запушены — возвращает matched=False
    (все квесты пройдены).

    Логика шага:
    - step_progress накапливается
    - пока step_progress < step.target_value — шаг не закрывается
    - при достижении target_value: начисляем reward_points,
      current_step += 1, step_progress = 0
    - если шагов больше нет — status = "completed"

    Возвращает:
      {
        "matched": bool,
        "quest_id": Optional[int],
        "step_completed": bool,
        "quest_completed": bool,
        "points_awarded": int,
        "auto_started": bool,     # ← флаг, что квест был автостартован
      }
    """
    result = {
        "matched": False,
        "quest_id": None,
        "step_completed": False,
        "quest_completed": False,
        "points_awarded": 0,
        "auto_started": False,
    }

    async with async_session() as session:
        # ---- 1. Все активные прогрессы, отсортированные по приоритету квеста ----
        rows = (await session.execute(
            select(UserQuestProgress, Quest)
            .join(Quest, Quest.id == UserQuestProgress.quest_id)
            .where(
                UserQuestProgress.user_id == user_id,
                UserQuestProgress.status == "in_progress",
                Quest.is_active.is_(True),
            )
            .order_by(Quest.sort_order)
        )).all()

        # ---- 2. АВТОСТАРТ: если активных нет — стартуем следующий ----
        if not rows:
            # Все quest_id, которые юзер уже начинал
            started_ids_subq = (
                select(UserQuestProgress.quest_id)
                .where(UserQuestProgress.user_id == user_id)
            )

            next_quest = (await session.execute(
                select(Quest)
                .where(Quest.is_active.is_(True))
                .where(Quest.id.notin_(started_ids_subq))
                .order_by(Quest.sort_order)
                .limit(1)
            )).scalar_one_or_none()

            if next_quest is None:
                # Все квесты юзер уже запускал — ничего не делаем
                return result

            prog = UserQuestProgress(
                user_id=user_id,
                quest_id=next_quest.id,
                current_step=1,
                step_progress=0,
                status="in_progress",
            )
            session.add(prog)
            await session.flush()

            rows = [(prog, next_quest)]
            result["auto_started"] = True
            logger.info(
                f"[QUESTS] user={user_id} auto-started quest='{next_quest.code}'"
            )

        # ---- 3. ПРОДВИЖЕНИЕ ----
        for prog, quest in rows:
            step = (await session.execute(
                select(QuestStep).where(
                    QuestStep.quest_id == prog.quest_id,
                    QuestStep.step_number == prog.current_step,
                )
            )).scalar_one_or_none()

            if step is None:
                # Шага нет — квест повреждён, помечаем завершённым
                prog.status = "completed"
                prog.completed_at = datetime.now(timezone.utc)
                continue

            if step.task_type != task_type:
                continue

            # Нашли подходящий квест — работаем только с ним
            result["matched"] = True
            result["quest_id"] = prog.quest_id

            prog.step_progress += amount

            if prog.step_progress >= step.target_value:
                # Шаг закрыт
                result["step_completed"] = True
                result["points_awarded"] = step.reward_points

                # Сколько всего шагов в квесте
                total_steps = (await session.execute(
                    select(QuestStep).where(QuestStep.quest_id == prog.quest_id)
                )).scalars().all()

                next_step_number = prog.current_step + 1

                if next_step_number > len(total_steps):
                    # Квест завершён
                    prog.status = "completed"
                    prog.completed_at = datetime.now(timezone.utc)
                    result["quest_completed"] = True
                else:
                    # Переход к следующему шагу
                    prog.current_step = next_step_number
                    prog.step_progress = 0

            await session.commit()
            break  # только один квест за вызов

    # Очки начисляем вне сессии
    if result["points_awarded"] > 0:
        try:
            await add_custom_points(user_id, result["points_awarded"])
        except Exception:
            logger.exception("[QUESTS] Failed to award points")

    if result["step_completed"]:
        logger.info(
            f"[QUESTS] user={user_id} task={task_type} "
            f"step_completed quest={result['quest_id']} "
            f"quest_completed={result['quest_completed']} "
            f"points={result['points_awarded']}"
        )

    return result