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
)
from admin import handlers as admin_handlers


def register_handlers(root_router: Router) -> None:
    root_router.include_router(admin_handlers.router)
    root_router.include_router(start.router)
    root_router.include_router(analysis.router)
    root_router.include_router(profile.router)
    root_router.include_router(matching.router)
    root_router.include_router(compare.router)
    root_router.include_router(tests.router)
    root_router.include_router(support.router)
    root_router.include_router(messaging.router)