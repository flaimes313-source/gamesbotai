from aiogram import F, Router
from aiogram.types import CallbackQuery

router = Router()


@router.callback_query(F.data == "tests_menu")
async def cb_tests(callback: CallbackQuery):
    await callback.answer()
    await callback.message.answer("🧪 Тесты появятся в следующем обновлении!")