import asyncio

from sqlalchemy import select

from database.connection import async_session
from database.models import Test


TESTS = [
    ("Какой ты лидер?", "Проверь свой стиль управления в игровом формате", 1),
    ("Какой ты друг?", "Что для тебя важнее в дружбе — хаос или стабильность", 2),
    ("Как ты ведёшь себя в конфликте?", "Огонь или лёд?", 3),
    ("Уровень харизмы", "Насколько сильно ты притягиваешь людей", 4),
    ("Уровень хаоса", "Сколько драмы ты приносишь в жизнь друзей", 5),
    ("Социальный архетип", "Кто ты в компании", 6),
    ("Какой ты человек в компании?", "Душа компании или наблюдатель", 7),
    ("Кто ты в споре?", "Логика, эмоции или юмор", 8),
    ("Насколько ты опасен для спокойной жизни?", "Серьёзный тест с долей юмора", 9),
    ("Твой стиль принятия решений", "Интуиция или анализ", 10),
]


async def seed_tests() -> None:
    async with async_session() as session:
        existing = (await session.execute(select(Test))).scalars().all()
        existing_names = {t.name for t in existing}

        added = 0
        for name, desc, order in TESTS:
            if name in existing_names:
                continue
            session.add(Test(name=name, description=desc, sort_order=order, is_active=True))
            added += 1

        await session.commit()
        print(f"[seed_tests] Added {added} tests.")


if __name__ == "__main__":
    asyncio.run(seed_tests())