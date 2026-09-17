import asyncio

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand

from bot.handlers import register_handlers
from config import config
from database.init_db import init_db
from utils.logging import get_logger, setup_logging

logger = get_logger(__name__)


async def set_commands(bot: Bot) -> None:
    commands = [
        BotCommand(command="start", description="Начать работу"),
        BotCommand(command="help", description="Помощь"),
        BotCommand(command="admin", description="Админ-панель"),
    ]
    await bot.set_my_commands(commands)


async def main() -> None:
    setup_logging()
    logger.info("Bot starting...")

    if not config.BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not set in .env")

    if not config.DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not set in .env")

    # создаём таблицы
    await init_db()

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