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
)
from admin import handlers as admin_handlers


def register_handlers(root_router: Router) -> None:
    """Регистрирует все роутеры в корневом Dispatcher."""
    # Админка — первой, чтобы /admin не перехватывался другими
    root_router.include_router(admin_handlers.router)

    # Основные пользовательские роутеры
    root_router.include_router(start.router)
    root_router.include_router(analysis.router)
    root_router.include_router(profile.router)
    root_router.include_router(matching.router)
    root_router.include_router(compare.router)
    root_router.include_router(tests.router)
    root_router.include_router(support.router)
    root_router.include_router(messaging.router)
    root_router.include_router(achievements.router)
    root_router.include_router(game_opt_in.router)
    root_router.include_router(privacy.router)
    root_router.include_router(payments.router)
    root_router.include_router(subscriptions.router)