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
    messaging,
    support,
)
from admin import handlers as admin_handlers


def register_handlers(root_router: Router) -> None:
    """
    Порядок регистрации роутеров:

    1. Админка — первой (чтобы /admin, /reply, /wl_add были приоритетны).
    2. Пользовательские с точными F.text == "..." — идут ДО catch-all.
    3. Catch-all роутеры (messaging, support) — в САМОМ КОНЦЕ.

    Внутри messaging.py и support.py catch-all хендлеры имеют
    динамический фильтр (_is_waiting_reply / _is_waiting_ticket),
    поэтому конфликтов между ними нет — порядок этих двух
    роутеров не критичен.
    """

    # ============================================================
    # 1. АДМИНКА
    # ============================================================
    root_router.include_router(admin_handlers.router)

    # ============================================================
    # 2. ПОЛЬЗОВАТЕЛЬСКИЕ (точные F.text == "...")
    # ============================================================
    root_router.include_router(start.router)          # /start, /help, «📸 Новый анализ»
    root_router.include_router(analysis.router)       # приём фото, do_share, new_analysis
    root_router.include_router(profile.router)        # «👤 Мой профиль», «📤 Поделиться», «⚙️ Настройки»
    root_router.include_router(matching.router)       # «🎯 Найти игроков» + режимы поиска
    root_router.include_router(compare.router)        # «👥 Сравнить»
    root_router.include_router(tests.router)          # «🧪 Пройти тест»
    root_router.include_router(achievements.router)   # «🏆 Достижения»
    root_router.include_router(game_opt_in.router)    # «🎮 Социальная игра»
    root_router.include_router(privacy.router)        # настройки приватности
    root_router.include_router(payments.router)       # «💎 PRO», промокоды
    root_router.include_router(subscriptions.router)  # обязательные подписки
    root_router.include_router(blocking.router)       # блокировка игроков
    root_router.include_router(advertising.router)    # клики по рекламе

    # ============================================================
    # 3. CATCH-ALL — В САМОМ КОНЦЕ
    # ============================================================
    # messaging.handle_custom_text — сработает ТОЛЬКО если пользователь
    # находится в PENDING_REPLY (ждёт отправки сообщения игроку)
    root_router.include_router(messaging.router)

    # support.handle_support_message — сработает ТОЛЬКО если пользователь
    # находится в PENDING_TICKET (ждёт отправки тикета)
    root_router.include_router(support.router)