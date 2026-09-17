from aiogram import Router

from bot.handlers import (
    start,
    analysis,
    profile,
    matching,
    compare,
    tests,
    support,
    messaging,
    achievements,
    game_opt_in,
    privacy,
    payments,
    subscriptions,
    blocking,
)
from admin import handlers as admin_handlers


def register_handlers(root_router: Router) -> None:
    """
    Регистрирует все роутеры в корневом Dispatcher.
    Порядок важен:
    1. Админка — первой, чтобы /admin и /start не пересекались.
    2. Хендлеры с точными совпадениями (callback_data) — раньше общих.
    3. Catch-all (например handle_custom_text) — последним.
    """
    # 1. Админка
    root_router.include_router(admin_handlers.router)

    # 2. Основные пользовательские
    root_router.include_router(start.router)
    root_router.include_router(analysis.router)
    root_router.include_router(profile.router)
    root_router.include_router(matching.router)
    root_router.include_router(compare.router)
    root_router.include_router(tests.router)
    root_router.include_router(support.router)
    root_router.include_router(messaging.router)  # содержит catch-all handle_custom_text
    root_router.include_router(achievements.router)
    root_router.include_router(game_opt_in.router)
    root_router.include_router(privacy.router)
    root_router.include_router(payments.router)
    root_router.include_router(subscriptions.router)
    root_router.include_router(blocking.router)