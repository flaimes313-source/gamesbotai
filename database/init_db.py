import asyncio

from sqlalchemy import text

from database.connection import engine
from database.models import Base


MIGRATIONS = [
    "ALTER TABLE support_tickets ADD COLUMN IF NOT EXISTS admin_id BIGINT;",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS timezone VARCHAR(64) NOT NULL DEFAULT 'Europe/Moscow';",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS timezone_confirmed BOOLEAN NOT NULL DEFAULT FALSE;",
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

    # Referral rewards
    "CREATE INDEX IF NOT EXISTS ix_referral_rewards_referrer_id ON referral_rewards (referrer_id);",
    "CREATE UNIQUE INDEX IF NOT EXISTS ix_referral_rewards_referred_id ON referral_rewards (referred_id);",

    # Reward claims
    "CREATE INDEX IF NOT EXISTS ix_reward_claims_user_id ON reward_claims (user_id);",
    "CREATE INDEX IF NOT EXISTS ix_reward_claims_reward_code ON reward_claims (reward_code);",

    # Weekly challenges
    "CREATE INDEX IF NOT EXISTS ix_weekly_challenges_week_start ON weekly_challenges (week_start);",
    "CREATE INDEX IF NOT EXISTS ix_user_weekly_challenges_user_id ON user_weekly_challenges (user_id);",
    "CREATE INDEX IF NOT EXISTS ix_user_weekly_challenges_challenge_id ON user_weekly_challenges (challenge_id);",

    # Quests — миграция колонки step_progress
    "ALTER TABLE user_quest_progress ADD COLUMN IF NOT EXISTS step_progress INTEGER NOT NULL DEFAULT 0;",

    # Quests — индексы
    "CREATE INDEX IF NOT EXISTS ix_quest_steps_quest_id ON quest_steps (quest_id);",
    "CREATE INDEX IF NOT EXISTS ix_user_quest_progress_user_id ON user_quest_progress (user_id);",
    "CREATE INDEX IF NOT EXISTS ix_user_quest_progress_quest_id ON user_quest_progress (quest_id);",

    # Legendary archetypes (Шаг 1.2)
    "ALTER TABLE user_engagement ADD COLUMN IF NOT EXISTS last_legendary_at TIMESTAMPTZ;",

    # ============================================================
    # Этап 1 — Уведомления (инфраструктура)
    # ============================================================

    # Настройки уведомлений
    """
    CREATE TABLE IF NOT EXISTS user_notification_settings (
        id SERIAL PRIMARY KEY,
        user_id INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
        daily_result_enabled BOOLEAN NOT NULL DEFAULT TRUE,
        horoscope_enabled BOOLEAN NOT NULL DEFAULT TRUE,
        secret_feature_enabled BOOLEAN NOT NULL DEFAULT TRUE,
        profile_views_enabled BOOLEAN NOT NULL DEFAULT TRUE,
        weekly_vibe_enabled BOOLEAN NOT NULL DEFAULT TRUE,
        tops_enabled BOOLEAN NOT NULL DEFAULT TRUE,
        premium_reminder_enabled BOOLEAN NOT NULL DEFAULT TRUE,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    """,
    "CREATE UNIQUE INDEX IF NOT EXISTS ix_user_notification_settings_user_id ON user_notification_settings (user_id);",

    # Просмотры профиля
    """
    CREATE TABLE IF NOT EXISTS profile_views (
        id SERIAL PRIMARY KEY,
        viewer_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        viewed_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        source VARCHAR(32) NOT NULL DEFAULT 'matching',
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    """,
    "CREATE INDEX IF NOT EXISTS ix_profile_views_viewer_id ON profile_views (viewer_id);",
    "CREATE INDEX IF NOT EXISTS ix_profile_views_viewed_id ON profile_views (viewed_id);",
    "CREATE INDEX IF NOT EXISTS ix_profile_views_created_at ON profile_views (created_at);",

    # Гороскопы
    """
    CREATE TABLE IF NOT EXISTS horoscopes (
        id SERIAL PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        date TIMESTAMPTZ NOT NULL,
        text TEXT NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CONSTRAINT uq_horoscope_user_date UNIQUE (user_id, date)
    );
    """,
    "CREATE INDEX IF NOT EXISTS ix_horoscopes_user_id ON horoscopes (user_id);",
    "CREATE INDEX IF NOT EXISTS ix_horoscopes_date ON horoscopes (date);",

    # ============================================================
    # Этап 4 — Рефакторинг loops на hub
    # ============================================================

    # Добавляем поле chat_reminder_enabled в существующую таблицу
    "ALTER TABLE user_notification_settings ADD COLUMN IF NOT EXISTS chat_reminder_enabled BOOLEAN NOT NULL DEFAULT TRUE;",
]


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with engine.begin() as conn:
        for sql in MIGRATIONS:
            try:
                await conn.execute(text(sql))
            except Exception as e:
                print(f"[init_db] migration warning: {e}", flush=True)

    print("[init_db] Tables created/updated successfully.", flush=True)


if __name__ == "__main__":
    asyncio.run(init_db())