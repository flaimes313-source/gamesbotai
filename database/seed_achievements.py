import asyncio
from sqlalchemy import select
from database.connection import async_session
from database.models import Achievement

ACHIEVEMENTS = [
    ("first_photo", "Первый анализ", "Загрузил первую фотографию", "📸"),
    ("first_share", "Поделился", "Поделился своим результатом", "📤"),
    ("friend_joined", "Привёл друга", "Друг зашёл по твоей ссылке", "👥"),
    ("first_test", "Первый тест", "Прошёл первый тест", "🧪"),
    ("chaos_90", "Хаос 90+", "Уровень хаоса выше 90", "🧨"),
    ("charisma_90", "Харизма 90+", "Уровень харизмы выше 90", "😎"),
    ("five_analyses", "5 анализов", "Прошёл анализ 5 раз", "🔥"),
]


async def seed_achievements() -> None:
    async with async_session() as session:
        existing = {a.code for a in (await session.execute(select(Achievement))).scalars().all()}
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