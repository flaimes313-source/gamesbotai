from aiogram import F, Router
from aiogram.types import CallbackQuery

router = Router()


@router.callback_query(F.data.startswith("msg_"))
async def cb_msg(callback: CallbackQuery):
    await callback.answer("Сообщения между игроками появятся в следующем обновлении!")


@router.callback_query(F.data.startswith("joke_"))
async def cb_joke(callback: CallbackQuery):
    await callback.answer("😂 Приколы появятся чуть позже!")


@router.callback_query(F.data == "close_msg")
async def cb_close(callback: CallbackQuery):
    await callback.answer()
    try:
        await callback.message.delete()
    except Exception:
        pass