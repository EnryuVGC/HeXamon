from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.ui.texts import text

router = Router()


@router.message(Command("pokeballs"))
async def pokeballs_command(message: Message) -> None:
    await message.reply(text("inventory.pokeballs_info"))
