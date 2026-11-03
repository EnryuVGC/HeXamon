import asyncio
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from bot.services import eggs
from bot.storage.stores import Stores
from bot.ui import battle_view
from bot.ui.texts import text

logger = logging.getLogger(__name__)

HATCH_CHECK_SECONDS = 30


async def hatch_eggs(bot: Bot, stores: Stores) -> None:
    while True:
        try:
            while (hatched := await eggs.hatch_next(stores)) is not None:
                name = battle_view.wild_name({"wild": hatched.pokemon})
                try:
                    await bot.send_message(hatched.trainer_id, text("hunt.egg_hatched", name=name))
                except TelegramAPIError as error:
                    logger.warning("Could not announce hatched egg: %s", error)
        except Exception:
            logger.exception("Could not hatch eggs")
        await asyncio.sleep(HATCH_CHECK_SECONDS)
