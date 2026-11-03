from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.ui.texts import text

router = Router()


@router.message(Command("commands"), F.from_user)
async def commands_command(message: Message) -> None:
    await message.reply(text("commands.list"))
