import asyncio

from database.connection import engine
from database.models import Base


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("[init_db] Tables created successfully.")


if __name__ == "__main__":
    asyncio.run(init_db())