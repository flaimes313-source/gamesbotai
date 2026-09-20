from aiogram import Router

from bot.handlers import (
    start,
    analysis,
    profile,
    matching,
    compare,
    tests,
    achievements,
    game_opt_in,
    privacy,
    payments,
    subscriptions,
    blocking,
    advertising,
    chats,
    messaging,
    support,
    timezone,
    engagement,
    info,
)
from admin import handlers as admin_handlers
from admin.broadcast import router as broadcast_router
from admin.subscriptions_wizard import router as subs_wizard_router


def register_handlers(root_router: Router) -> None:
    # 1. Админка + FSM-мастера
    root_router.include_router(admin_handlers.router)
    root_router.include_router(subs_wizard_router)
    root_router.include_router(broadcast_router)

    # 2. Пользовательские
    root_router.include_router(start.router)
    root_router.include_router(analysis.router)
    root_router.include_router(profile.router)
    root_router.include_router(timezone.router)
    root_router.include_router(engagement.router)
    root_router.include_router(info.router)         # ← О боте
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

    # 3. Чаты
    root_router.include_router(chats.router)

    # 4. Catch-all
    root_router.include_router(messaging.router)
    root_router.include_router(support.router)