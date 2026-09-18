from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def chat_actions_kb(
    chat_id: int,
    other_username: str | None = None,
    is_pro: bool = False,
) -> InlineKeyboardMarkup:
    """
    Клавиатура под открытым чатом.
    Если is_pro — добавляем AI-кнопки.
    """
    rows = [
        [InlineKeyboardButton(
            text="✍️ Ответить",
            callback_data=f"chat_reply_{chat_id}",
        )],
    ]

    if is_pro:
        rows.append([InlineKeyboardButton(
            text="🤖 Помоги ответить",
            callback_data=f"chat_ai_reply_{chat_id}",
        )])
        rows.append([InlineKeyboardButton(
            text="📊 Анализ переписки",
            callback_data=f"chat_ai_analyze_{chat_id}",
        )])
    else:
        rows.append([InlineKeyboardButton(
            text="🤖 Помоги ответить 💎",
            callback_data=f"chat_ai_locked_{chat_id}",
        )])

    rows.append([InlineKeyboardButton(
        text="🔄 Обновить",
        callback_data=f"chat_open_{chat_id}",
    )])

    if other_username:
        rows.append([InlineKeyboardButton(
            text=f"👤 @{other_username} в Telegram",
            url=f"https://t.me/{other_username}",
        )])

    rows.append([InlineKeyboardButton(
        text="⬅️ К списку чатов",
        callback_data="chat_list",
    )])

    return InlineKeyboardMarkup(inline_keyboard=rows)


def chat_list_back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🏠 В главное меню", callback_data="back_to_main")],
        ]
    )


def chat_ai_suggestions_kb(chat_id: int) -> InlineKeyboardMarkup:
    """Клавиатура с вариантами ответа — подставляются динамически."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="⬅️ К чату",
                callback_data=f"chat_open_{chat_id}",
            )],
        ]
    )