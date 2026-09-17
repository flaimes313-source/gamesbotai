import asyncio

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand

from bot.handlers import register_handlers
from config import config
from database.init_db import init_db
from database.seed_tests import seed_tests
from database.seed_achievements import seed_achievements
from utils.logging import get_logger, setup_logging
from webhook_server import run_server

logger = get_logger(__name__)


async def set_commands(bot: Bot) -> None:
    await bot.set_my_commands([
        BotCommand(command="start", description="Начать работу"),
        BotCommand(command="help", description="Помощь"),
        BotCommand(command="admin", description="Админ-панель"),
    ])


async def main() -> None:
    setup_logging()
    logger.info("Bot starting...")

    if not config.BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not set")
    if not config.DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not set")

    await init_db()
    await seed_tests()
    await seed_achievements()

    # Запускаем webhook-сервер (YooKassa)
    try:
        await run_server(port=8080)
    except OSError as e:
        logger.warning(f"Webhook server not started: {e}")

    bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    register_handlers(dp)

    await set_commands(bot)

    logger.info("Polling started.")
    await dp.start_polling(bot, skip_updates=True)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped.")