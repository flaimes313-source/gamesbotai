from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy import select

from database.connection import async_session
from database.models import Match, User

router = Router()


@router.callback_query(F.data.startswith("block_"))
async def cb_block(callback: CallbackQuery):
    await callback.answer()
    target_id = int(callback.data.replace("block_", ""))

    async with async_session() as session:
        me = (await session.execute(select(User).where(User.telegram_id == callback.from_user.id))).scalar_one_or_none()
        if me is None:
            return

        # Удаляем все матчи с этим пользователем
        matches = (await session.execute(
            select(Match).where(
                ((Match.user1_id == me.id) & (Match.user2_id == target_id)) |
                ((Match.user1_id == target_id) & (Match.user2_id == me.id))
            )
        )).scalars().all()
        for m in matches:
            m.status = "blocked"
        await session.commit()

    await callback.message.answer("🚫 Игрок заблокирован. Больше не появится в поиске.")