import logging

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandObject
from aiogram.types import Message, ReplyParameters

from bot.game import encounters
from bot.game import inventory as rules
from bot.handlers.journey import JourneyRequired
from bot.services import inventory
from bot.storage.stores import Stores
from bot.ui import inventory_view
from bot.ui.texts import text

logger = logging.getLogger(__name__)

router = Router()
router.message.middleware(JourneyRequired())


@router.message(Command(*rules.stone_commands(), ignore_case=True), F.from_user)
async def key_item_command(message: Message, command: CommandObject, stores: Stores) -> None:
    stone = rules.stone_of_command(command.command)
    owned = await inventory.inventory_of(stores, message.from_user.id)
    if owned is None or stone not in owned.mega_stones:
        await message.reply(text("inventory.no_key_item"))
        return
    caption = inventory_view.stone_card(stone)
    try:
        await message.bot.copy_message(
            message.chat.id,
            encounters.STONE_IMAGES_CHANNEL,
            encounters.stone_image_id(stone),
            caption=caption,
            reply_parameters=ReplyParameters(message_id=message.message_id, allow_sending_without_reply=True),
        )
    except TelegramAPIError as error:
        logger.warning("Could not send the %s picture to %s: %s", stone, message.chat.id, error)
        await message.reply(caption)
