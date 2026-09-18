import asyncio

from database.connection import async_session
from database.models import User
from services.chats import (
    get_or_create_chat,
    get_chat_messages,
    list_user_chats,
    send_chat_message,
)
from sqlalchemy import select


async def main():
    async with async_session() as session:
        # Найти двух пользователей
        users = (await session.execute(select(User).limit(2))).scalars().all()
        if len(users) < 2:
            print("❌ Нужны как минимум 2 пользователя в БД")
            return

        a, b = users[0], users[1]
        print(f"A: id={a.id} tg={a.telegram_id}")
        print(f"B: id={b.id} tg={b.telegram_id}")

        # Создать чат
        chat = await get_or_create_chat(session, a.id, b.id)
        print(f"✅ Чат создан: id={chat.id} ({chat.user1_id} <-> {chat.user2_id})")

        # Отправить сообщение от A к B (bot=None — только БД, без доставки)
        msg = await send_chat_message(
            bot=None,  # доставка не нужна для теста
            sender_telegram_id=a.telegram_id,
            chat_id=chat.id,
            text="Привет, это тестовое сообщение!",
        )
        print(f"✅ Сообщение отправлено: id={msg.id if msg else None}")

        # Прочитать историю
        msgs = await get_chat_messages(session, chat.id)
        print(f"✅ История: {len(msgs)} сообщений")
        for m in msgs:
            print(f"   [{m.sender_id}→{m.receiver_id}]: {m.text}")

        # Список чатов
        chats_a = await list_user_chats(session, a.id)
        print(f"✅ Чаты A: {len(chats_a)}")
        for c in chats_a:
            print(f"   chat {c['chat_id']}: {c['other_name']} (unread={c['unread_count']})")


if __name__ == "__main__":
    asyncio.run(main())