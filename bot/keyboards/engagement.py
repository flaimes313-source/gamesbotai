from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


# ============================================================
# ЧЕЛЛЕНДЖ ДНЯ
# ============================================================
def challenge_kb(challenge: dict) -> InlineKeyboardMarkup:
    """Клавиатура под челленджем дня."""
    task_type = challenge.get("task_type", "")
    status = challenge.get("status", "in_progress")

    rows = []

    if status == "completed":
        rows.append([InlineKeyboardButton(
            text="✅ Выполнено!",
            callback_data="challenge_noop",
        )])
    else:
        # Кнопка действия в зависимости от типа задания
        action_map = {
            "photo": ("📸 Отправить фото", "new_analysis"),
            "analysis": ("📸 Сделать анализ", "new_analysis"),
            "test": ("🧪 Пройти тест", "tests_menu"),
            "message": ("💬 Мои чаты", "chat_list"),
            "invite": ("📤 Поделиться", "share_profile"),
            "share": ("📤 Поделиться", "share_profile"),
            "compare": ("👥 Сравнить", "compare_menu"),
        }
        action_text, action_callback = action_map.get(
            task_type,
            ("🎯 Выполнить", "challenge_noop"),
        )
        rows.append([InlineKeyboardButton(
            text=action_text,
            callback_data=action_callback,
        )])

    rows.append([InlineKeyboardButton(
        text="🏠 В главное меню",
        callback_data="back_to_main",
    )])

    return InlineKeyboardMarkup(inline_keyboard=rows)


# ============================================================
# МОЯ СТАТИСТИКА
# ============================================================
def stats_back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="🎯 Челлендж дня",
                callback_data="challenge_today",
            )],
            [InlineKeyboardButton(
                text="🏠 В главное меню",
                callback_data="back_to_main",
            )],
        ]
    )


# ============================================================
# УРОВЕНЬ
# ============================================================
def level_back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="📊 Моя статистика",
                callback_data="my_stats",
            )],
            [InlineKeyboardButton(
                text="🎯 Челлендж дня",
                callback_data="challenge_today",
            )],
            [InlineKeyboardButton(
                text="🏠 В главное меню",
                callback_data="back_to_main",
            )],
        ]
    )


# ============================================================
# ТОПЫ
# ============================================================
def tops_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="🔥 По хаосу",
                callback_data="top_chaos",
            )],
            [InlineKeyboardButton(
                text="😂 По юмору",
                callback_data="top_humor",
            )],
            [InlineKeyboardButton(
                text="✨ По харизме",
                callback_data="top_charisma",
            )],
            [InlineKeyboardButton(
                text="🏆 По очкам",
                callback_data="top_points",
            )],
            [InlineKeyboardButton(
                text="👥 По друзьям",
                callback_data="top_referrals",
            )],
            [InlineKeyboardButton(
                text="🏠 В главное меню",
                callback_data="back_to_main",
            )],
        ]
    )


def tops_back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="⬅️ К топам",
                callback_data="tops_menu",
            )],
            [InlineKeyboardButton(
                text="🏠 В главное меню",
                callback_data="back_to_main",
            )],
        ]
    )