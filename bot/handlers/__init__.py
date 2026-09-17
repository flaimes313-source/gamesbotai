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
    advertising,
)
from admin import handlers as admin_handlers


def register_handlers(root_router: Router) -> None:
    """
    Порядок важен:
    1. Админка — первой.
    2. Специализированные хендлеры с точными callback_data.
    3. Catch-all (support.handle_support_message, messaging.handle_custom_text) — последними,
       чтобы не перехватывать reply-кнопки.
    """
    # 1. Админка
    root_router.include_router(admin_handlers.router)

    # 2. Пользовательские
    root_router.include_router(start.router)
    root_router.include_router(analysis.router)
    root_router.include_router(profile.router)
    root_router.include_router(matching.router)
    root_router.include_router(compare.router)
    root_router.include_router(tests.router)
    root_router.include_router(achievements.router)
    root_router.include_router(game_opt_in.router)
    root_router.include_router(privacy.router)
    root_router.include_router(payments.router)
    root_router.include_router(subscriptions.router)
    root_router.include_router(blocking.router)
    root_router.include_router(advertising.router)

    # 3. Catch-all — в самом конце
    root_router.include_router(messaging.router)
    root_router.include_router(support.router)