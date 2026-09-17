from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def modes_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎯 Похожий на меня", callback_data="mode_similar")],
            [InlineKeyboardButton(text="🔄 Моя противоположность", callback_data="mode_opposite")],
            [InlineKeyboardButton(text="😂 Самый смешной", callback_data="mode_funny")],
            [InlineKeyboardButton(text="😎 Самый харизматичный", callback_data="mode_charismatic")],
            [InlineKeyboardButton(text="🧠 Интеллектуальный соперник 💎", callback_data="mode_intellectual")],
            [InlineKeyboardButton(text="🧨 Максимальный хаос 💎", callback_data="mode_chaos")],
            [InlineKeyboardButton(text="🎲 Случайный игрок", callback_data="mode_random")],
        ]
    )


def match_actions_kb(target_user_id: int, score: int = 0) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💬 Написать сообщение", callback_data=f"msg_{target_user_id}")],
            [InlineKeyboardButton(text="😂 Отправить прикол", callback_data=f"joke_{target_user_id}")],
            [InlineKeyboardButton(text="🎯 Следующий", callback_data="next_candidate")],
            [InlineKeyboardButton(text="🚫 Заблокировать", callback_data=f"block_{target_user_id}")],
        ]
    )