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
)
from admin import handlers as admin_handlers


def register_handlers(root_router: Router) -> None:
    """
    Порядок регистрации:
    1. Админка — первой.
    2. Точные reply-хендлеры и callback-и.
    3. Чаты — до messaging (там есть catch-all).
    4. Catch-all (messaging, support) — в самом конце.
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

    # 3. Чаты — с catch-all для ввода текста
    root_router.include_router(chats.router)

    # 4. Приколы, стили, catch-all для «прикола»
    root_router.include_router(messaging.router)

    # 5. Поддержка — последней
    root_router.include_router(support.router)