import asyncio
import os
import sys
import traceback
from datetime import datetime, timezone


def _log_boot(msg: str) -> None:
    print(f"[BOOT {datetime.now(timezone.utc).isoformat()}] {msg}", flush=True)


_log_boot("=== PROCESS START ===")

try:
    _log_boot("Importing aiogram...")
    from aiogram import Bot, Dispatcher
    from aiogram.client.default import DefaultBotProperties
    from aiogram.enums import ParseMode
    from aiogram.fsm.storage.memory import MemoryStorage
    from aiogram.types import BotCommand, BotCommandScopeChat, BotCommandScopeDefault

    _log_boot("Importing config...")
    from config import config

    _log_boot("Importing database...")
    from database.init_db import init_db
    from database.seed_achievements import seed_achievements
    from database.seed_tests import seed_tests

    _log_boot("Importing feature flags...")
    from services.feature_flags import ensure_flags_exist

    _log_boot("Importing middlewares...")
    from bot.middlewares.feature_flags import BotEnabledMiddleware
    from bot.middlewares.mandatory_subscription import MandatorySubscriptionMiddleware

    _log_boot("Importing handlers...")
    from bot.handlers import register_handlers

    _log_boot("Importing utils...")
    from utils.logging import get_logger, setup_logging

    _log_boot("Importing webhook_server...")
    from webhook_server import run_server

    _log_boot("Importing daily_sender...")
    from services.notifications.daily_sender import daily_loop

    _log_boot("Importing chat_reminder...")
    from services.notifications.chat_reminder import chat_reminder_loop

    _log_boot("Importing db_cleanup...")
    from services.notifications.db_cleanup import db_cleanup_loop

    _log_boot("Importing premium_reminder...")
    from services.notifications.premium_reminder import premium_reminder_loop

    _log_boot("Importing tops_sender...")
    from services.notifications.tops_sender import tops_loop

    _log_boot("Importing weekly vibe sender...")
    from services.notifications.vibe_weekly import weekly_vibe_loop

    _log_boot("Importing notification hub...")
    from services.notifications.hub import notification_worker_loop

    _log_boot("All imports OK")
except Exception as e:
    print(f"[BOOT ERROR] Import failed: {e}", flush=True)
    traceback.print_exc()
    sys.exit(1)


async def setup_commands(bot: Bot) -> None:
    public_commands = [
        BotCommand(command="start", description="Узнать свой вайб"),
        BotCommand(command="help", description="Помощь"),
    ]
    await bot.set_my_commands(public_commands, scope=BotCommandScopeDefault())

    admin_commands = public_commands + [
        BotCommand(command="admin", description="Админ-панель"),
        BotCommand(command="wl_add", description="Добавить в whitelist"),
        BotCommand(command="wl_remove", description="Удалить из whitelist"),
    ]
    for admin_id in config.ADMIN_IDS:
        try:
            await bot.set_my_commands(
                admin_commands,
                scope=BotCommandScopeChat(chat_id=admin_id),
            )
        except Exception as e:
            print(f"[BOOT] Failed to set admin commands for {admin_id}: {e}", flush=True)


async def main() -> None:
    _log_boot("Entering main()")
    setup_logging()
    logger = get_logger(__name__)

    logger.info("Bot starting...")
    logger.info(f"BOT_TOKEN present: {bool(config.BOT_TOKEN)}")
    logger.info(f"DATABASE_URL present: {bool(config.DATABASE_URL)}")
    logger.info(f"GIGACHAT_API_KEY present: {bool(config.GIGACHAT_API_KEY)}")
    logger.info(f"ADMIN_IDS: {config.ADMIN_IDS}")

    if not config.BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not set")
    if not config.DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not set")

    logger.info("Calling init_db()...")
    await init_db()

    logger.info("Seeding feature flags...")
    await ensure_flags_exist()

    logger.info("Seeding tests...")
    await seed_tests()

    logger.info("Seeding achievements...")
    await seed_achievements()

    logger.info("Seeding quests...")
    try:
        from services.engagement.quests import seed_quests
        await seed_quests()
    except Exception:
        logger.exception("Failed to seed quests")

    logger.info("Starting webhook server...")
    port = int(os.getenv("PORT", "8080"))
    try:
        await run_server(port=port)
    except OSError as e:
        logger.warning(f"Webhook server not started: {e}")
    except Exception:
        logger.exception("Webhook server failed")

    logger.info("Creating Bot instance...")
    bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    logger.info("Creating Dispatcher with MemoryStorage (no Redis)...")
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    logger.info("Registering middlewares...")
    dp.update.middleware(BotEnabledMiddleware())
    dp.message.middleware(MandatorySubscriptionMiddleware())
    dp.callback_query.middleware(MandatorySubscriptionMiddleware())

    logger.info("Registering handlers...")
    register_handlers(dp)

    logger.info("Setting bot commands...")
    await setup_commands(bot)

    logger.info("Starting daily notification loop...")
    try:
        asyncio.create_task(daily_loop(bot))
    except Exception:
        logger.exception("Failed to start daily loop")

    logger.info("Starting chat reminder loop...")
    try:
        asyncio.create_task(chat_reminder_loop(bot))
    except Exception:
        logger.exception("Failed to start chat reminder loop")

    logger.info("Starting DB cleanup loop...")
    try:
        asyncio.create_task(db_cleanup_loop())
    except Exception:
        logger.exception("Failed to start DB cleanup loop")

    logger.info("Starting premium reminder loop...")
    try:
        asyncio.create_task(premium_reminder_loop(bot))
    except Exception:
        logger.exception("Failed to start premium reminder loop")

    logger.info("Starting tops loop...")
    try:
        asyncio.create_task(tops_loop(bot))
    except Exception:
        logger.exception("Failed to start tops loop")

    logger.info("Starting weekly vibe loop...")
    try:
        asyncio.create_task(weekly_vibe_loop(bot))
    except Exception:
        logger.exception("Failed to start weekly vibe loop")

    logger.info("Starting notification hub worker...")
    try:
        asyncio.create_task(notification_worker_loop(bot))
    except Exception:
        logger.exception("Failed to start notification hub worker")

    logger.info("Polling started.")
    try:
        await dp.start_polling(
            bot,
            skip_updates=True,
            handle_as_tasks=True,
            tasks_concurrency_limit=50,
        )
    except TypeError:
        logger.warning("handle_as_tasks not supported, fallback to default polling")
        await dp.start_polling(bot, skip_updates=True)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        _log_boot("Bot stopped by signal.")
    except Exception as e:
        print(f"[FATAL] {e}", flush=True)
        traceback.print_exc()
        sys.exit(1)