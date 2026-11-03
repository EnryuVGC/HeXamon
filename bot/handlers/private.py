from functools import wraps
from typing import Any, Awaitable, Callable

from aiogram import F, Router
from aiogram.dispatcher.event.bases import SkipHandler
from aiogram.dispatcher.event.handler import CallableObject
from aiogram.enums import ChatType
from aiogram.filters import CommandObject, CommandStart
from aiogram.types import Message
from aiogram.utils.deep_linking import create_start_link

from bot.services import onboarding
from bot.ui.keyboards import open_private_chat_keyboard
from bot.ui.texts import text

router = Router()

_private_commands: dict[str, Callable[..., Awaitable[Any]]] = {}


def private_only(command: str) -> Callable:
    def decorator(handler: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
        @wraps(handler)
        async def wrapper(message: Message, *args: Any, **kwargs: Any) -> Any:
            if message.chat.type == ChatType.PRIVATE:
                return await handler(message, *args, **kwargs)
            link = await create_start_link(message.bot, command)
            await message.reply(
                text("common.private_only"),
                reply_markup=open_private_chat_keyboard(link),
            )

        _private_commands[command] = wrapper
        return wrapper

    return decorator


@router.message(CommandStart(deep_link=True), F.from_user)
async def run_linked_command(message: Message, command: CommandObject, **data: Any) -> Any:
    handler = _private_commands.get(command.args)
    if handler is None or not await onboarding.has_started(data["stores"], message.from_user.id):
        raise SkipHandler
    return await CallableObject(handler).call(message, command=command, **data)
