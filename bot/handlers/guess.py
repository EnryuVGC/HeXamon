import asyncio
import logging
from html import escape
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware, F, Router
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from aiogram.types import Message, TelegramObject

from bot.game import guessing as rules
from bot.handlers.journey import JourneyRequired
from bot.services import guessing
from bot.storage.stores import Stores
from bot.ui.texts import text

router = Router()
router.message.middleware(JourneyRequired())

logger = logging.getLogger(__name__)

GROUP_CHATS = (ChatType.GROUP, ChatType.SUPERGROUP)

_timers: set[asyncio.Task] = set()


class GuessAnswers(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if await _answered(event, data["stores"]):
            return None
        return await handler(event, data)


async def _answered(message: Message, stores: Stores) -> bool:
    if not message.text or message.from_user is None or message.chat.type not in GROUP_CHATS:
        return False
    game_round = guessing.open_round(message.chat.id)
    if game_round is None or not rules.is_correct(message.text, game_round.answer):
        return False
    trainer = message.from_user
    if not await stores.trainers.has_started(trainer.id):
        return False
    won = await guessing.claim_win(stores, message.chat.id, game_round, trainer.id)
    if won is None:
        return False
    seconds, paid = won
    await message.reply(
        text(
            "guess.won" if paid else "guess.won_limit",
            trainer_id=trainer.id,
            trainer=escape(trainer.first_name),
            seconds=f"{seconds:.2f}",
            name=game_round.answer,
            reward=paid,
        )
    )
    return True


async def _run_timer(message: Message, game_round: guessing.GuessRound) -> None:
    chat_id = message.chat.id
    try:
        await asyncio.sleep(rules.HINT_AFTER_SECONDS)
        if not guessing.is_running(chat_id, game_round):
            return
        hint = rules.make_hint(game_round.answer)
        await message.answer(text("guess.hint", hint=escape(hint), seconds=rules.HINT_SECONDS))
        await asyncio.sleep(rules.HINT_SECONDS)
        if guessing.is_running(chat_id, game_round):
            guessing.cancel(chat_id, game_round)
            await message.answer(text("guess.nobody", name=game_round.answer))
    except TelegramAPIError:
        guessing.cancel(chat_id, game_round)
        logger.info("Could not finish guess round in chat %s", chat_id)


@router.message(Command("minigames"), F.from_user)
async def minigames_command(message: Message) -> None:
    await message.reply(text("guess.minigames"))


@router.message(Command("guess"), F.from_user)
async def guess_command(message: Message) -> None:
    if message.chat.type not in GROUP_CHATS:
        await message.reply(text("guess.groups_only"))
        return
    game_round = guessing.reserve(message.chat.id)
    if game_round is None:
        await message.reply(text("guess.already_running"))
        return
    try:
        await message.reply_photo(game_round.image, caption=text("guess.start"))
    except TelegramAPIError:
        guessing.cancel(message.chat.id, game_round)
        raise
    guessing.start(game_round)
    timer = asyncio.create_task(_run_timer(message, game_round))
    _timers.add(timer)
    timer.add_done_callback(_timers.discard)
