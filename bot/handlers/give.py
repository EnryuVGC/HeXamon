from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from bot.handlers.journey import JourneyRequired
from bot.services import gifts
from bot.storage.stores import Stores
from bot.ui.texts import text

router = Router()
router.message.middleware(JourneyRequired())

REPLIES = {
    gifts.SENT: "give.sent",
    gifts.BAD_AMOUNT: "give.usage",
    gifts.NOT_STARTED: "give.not_started",
    gifts.NO_MONEY: "give.no_money",
}


@router.message(Command("give"), F.from_user)
async def give_command(message: Message, command: CommandObject, stores: Stores) -> None:
    replied = message.reply_to_message
    receiver = replied.from_user if replied and not replied.forum_topic_created else None
    if receiver is None:
        await message.reply(text("give.usage"))
        return
    if receiver.id == message.from_user.id:
        await message.reply(text("give.self"))
        return
    if receiver.is_bot:
        await message.reply(text("give.bot"))
        return

    status = await gifts.give(stores, message.from_user.id, receiver.id, command.args)
    await message.reply(text(REPLIES[status]))
