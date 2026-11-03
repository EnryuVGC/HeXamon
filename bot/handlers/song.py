import logging

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from aiogram.types import Message, ReplyParameters

from bot.ui.texts import text

logger = logging.getLogger(__name__)

SONG_CHANNEL = "@HeXaAssets"
SONG_POST = 627

router = Router()


@router.message(Command("song"), F.from_user)
async def song_command(message: Message) -> None:
    try:
        await message.bot.copy_message(
            message.chat.id,
            SONG_CHANNEL,
            SONG_POST,
            reply_parameters=ReplyParameters(message_id=message.message_id, allow_sending_without_reply=True),
        )
    except TelegramAPIError as error:
        logger.warning("Could not send the song to %s: %s", message.chat.id, error)
        await message.reply(text("song.unavailable"))
