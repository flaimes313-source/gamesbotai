import asyncio

from sqlalchemy import select

from database.connection import async_session
from database.models import Achievement


ACHIEVEMENTS = [
    # === Базовые (этап 1) ===
    ("first_photo", "Первый анализ", "Загрузил первую фотографию", "📸"),
    ("first_share", "Поделился", "Поделился своим результатом", "📤"),
    ("friend_joined", "Привёл друга", "Друг зашёл по твоей ссылке", "👥"),
    ("first_test", "Первый тест", "Прошёл первый тест", "🧪"),
    ("five_tests", "5 тестов", "Прошёл 5 тестов", "🎓"),
    ("chaos_90", "Хаос 90+", "Уровень хаоса выше 90", "🧨"),
    ("charisma_90", "Харизма 90+", "Уровень харизмы выше 90", "😎"),
    ("five_analyses", "5 анализов", "Прошёл анализ 5 раз", "🔥"),
    ("first_match", "Первый матч", "Нашёл первого игрока", "🎯"),
    ("ten_messages", "10 сообщений", "Отправил 10 сообщений", "💬"),
    ("pro_first", "PRO-игрок", "Оформил первую PRO-подписку", "💎"),

    # === Стрики (этап 6.1) ===
    ("streak_3", "3 дня подряд", "Заходил в бота 3 дня подряд", "🔥"),
    ("streak_7", "Неделя с Вайбми", "Заходил в бота 7 дней подряд", "📅"),
    ("streak_14", "2 недели подряд", "Заходил в бота 14 дней подряд", "🗓"),
    ("streak_30", "Месяц с Вайбми", "Заходил в бота 30 дней подряд", "🏅"),
    ("streak_100", "100 дней подряд", "Заходил в бота 100 дней подряд", "👑"),

    # === Уровни (этап 6.1) ===
    ("level_5", "Постоянный", "Достиг 5 уровня", "🥉"),
    ("level_10", "Гуру вайба", "Достиг 10 уровня", "🥈"),
    ("level_15", "Архитектор вайбов", "Достиг 15 уровня", "🥇"),
    ("level_20", "ЛЕГЕНДА ВАЙБМИ", "Достиг максимального уровня", "👑"),
]


async def seed_achievements() -> None:
    async with async_session() as session:
        existing = {
            a.code for a in (await session.execute(select(Achievement))).scalars().all()
        }
        added = 0
        for code, title, desc, emoji in ACHIEVEMENTS:
            if code in existing:
                continue
            session.add(Achievement(code=code, title=title, description=desc, emoji=emoji))
            added += 1
        await session.commit()
        print(f"[seed_achievements] Added {added}")


if __name__ == "__main__":
    asyncio.run(seed_achievements())