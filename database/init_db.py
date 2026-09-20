import asyncio

from sqlalchemy import text

from database.connection import engine
from database.models import Base


# ============================================================
# Safe-миграции: добавляем столбцы, которых нет.
# Работает через IF NOT EXISTS — безопасно повторять.
# ============================================================
MIGRATIONS = [
    # support_tickets
    "ALTER TABLE support_tickets ADD COLUMN IF NOT EXISTS admin_id BIGINT;",

    # users — timezone
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS timezone VARCHAR(64) NOT NULL DEFAULT 'Europe/Moscow';",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS timezone_confirmed BOOLEAN NOT NULL DEFAULT FALSE;",

    # chat_reports
    """
    CREATE TABLE IF NOT EXISTS chat_reports (
        id SERIAL PRIMARY KEY,
        chat_id INTEGER NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
        reporter_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        target_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        reason TEXT,
        status VARCHAR(16) NOT NULL DEFAULT 'open',
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    """,
    "CREATE INDEX IF NOT EXISTS ix_chat_reports_chat_id ON chat_reports (chat_id);",
    "CREATE INDEX IF NOT EXISTS ix_chat_reports_target_id ON chat_reports (target_id);",

    # Engagement
    "CREATE INDEX IF NOT EXISTS ix_user_engagement_user_id ON user_engagement (user_id);",
    "CREATE INDEX IF NOT EXISTS ix_daily_challenges_date ON daily_challenges (date);",
    "CREATE INDEX IF NOT EXISTS ix_user_challenges_user_id ON user_challenges (user_id);",
    "CREATE INDEX IF NOT EXISTS ix_user_challenges_challenge_id ON user_challenges (challenge_id);",
]


async def init_db() -> None:
    # 1. Создаём отсутствующие таблицы
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # 2. Догоняем недостающие столбцы и таблицы
    async with engine.begin() as conn:
        for sql in MIGRATIONS:
            try:
                await conn.execute(text(sql))
            except Exception as e:
                print(f"[init_db] migration warning: {e}", flush=True)

    print("[init_db] Tables created/updated successfully.", flush=True)


if __name__ == "__main__":
    asyncio.run(init_db())