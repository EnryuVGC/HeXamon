from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.handlers.journey import JourneyRequired
from bot.handlers.private import private_only
from bot.services import onboarding, reply_keyboard
from bot.storage.stores import Stores
from bot.ui.keyboards import close_keyboard, main_keyboard
from bot.ui.texts import text

router = Router()
router.message.middleware(JourneyRequired())


@router.message(Command("open"), F.from_user)
@private_only("open")
async def open_command(message: Message, stores: Stores) -> None:
    trainer_id = message.from_user.id
    if not await onboarding.has_started(stores, trainer_id):
        await message.reply(text("common.start_journey"))
        return
    await reply_keyboard.mark_open(stores, trainer_id)
    await message.answer(text("common.keyboard_opened"), reply_markup=main_keyboard())


@router.message(Command("close"), F.from_user)
async def close_command(message: Message, stores: Stores) -> None:
    await reply_keyboard.mark_closed(stores, message.from_user.id)
    await message.reply(text("common.keyboard_closed"), reply_markup=close_keyboard())
