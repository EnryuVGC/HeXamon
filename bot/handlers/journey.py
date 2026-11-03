from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.enums import ChatType
from aiogram.types import Message
from aiogram.utils.deep_linking import create_start_link

from bot.services import onboarding
from bot.ui.keyboards import open_private_chat_keyboard
from bot.ui.texts import text

START_LINK_COMMAND = "start"


class JourneyRequired(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Message, dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: dict[str, Any],
    ) -> Any:
        if event.from_user is None or await onboarding.has_started(data["stores"], event.from_user.id):
            return await handler(event, data)

        keyboard = None
        if event.chat.type != ChatType.PRIVATE:
            link = await create_start_link(event.bot, START_LINK_COMMAND)
            keyboard = open_private_chat_keyboard(link)
        await event.reply(text("common.start_journey"), reply_markup=keyboard)
