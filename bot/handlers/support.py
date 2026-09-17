from aiogram import F, Router
from aiogram.types import Message

router = Router()


@router.message(F.text == "🆘 Поддержка")
async def support_msg(message: Message):
    await message.answer("Напиши свой вопрос одним сообщением — и мы передадим его в поддержку.")