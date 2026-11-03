import asyncio
import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.utils.deep_linking import create_start_link

from bot.game import encounters
from bot.game import referrals as rules
from bot.handlers.journey import JourneyRequired
from bot.services import referrals
from bot.storage.stores import Stores
from bot.ui import referrals_view
from bot.ui.texts import text

logger = logging.getLogger(__name__)

PAYOUT_CHECK_SECONDS = 30

router = Router()
router.message.middleware(JourneyRequired())


@router.message(Command("referrals"), F.from_user)
async def referrals_command(message: Message, stores: Stores) -> None:
    trainer_id = message.from_user.id
    await message.reply(referrals_view.stats_text(await referrals.referral_count(stores, trainer_id)))
    link = await create_start_link(message.bot, rules.link_payload(trainer_id))
    await message.answer(text("referrals.invite", link=link))


async def _send_quietly(bot: Bot, chat_id: int, body: str) -> None:
    try:
        await bot.send_message(chat_id, body)
    except TelegramAPIError:
        pass


async def _announce_stone(bot: Bot, chat_id: int, count: int, stone: str) -> None:
    caption = referrals_view.stone_text(count, stone)
    try:
        await bot.copy_message(
            chat_id,
            encounters.STONE_IMAGES_CHANNEL,
            encounters.stone_image_id(stone),
            caption=caption,
        )
    except TelegramAPIError as error:
        logger.warning("Could not send the %s picture to %s: %s", stone, chat_id, error)
        await _send_quietly(bot, chat_id, caption)


async def _announce_payout(bot: Bot, payout: referrals.Payout) -> None:
    body = referrals_view.payout_text(payout.name, payout.count, payout.milestone, payout.bonus)
    await _send_quietly(bot, payout.referrer_id, body)
    if payout.milestone.stone:
        await _announce_stone(bot, payout.referrer_id, payout.count, payout.milestone.stone)


async def pay_referrals(bot: Bot, stores: Stores) -> None:
    while True:
        try:
            while (payout := await referrals.next_payout(stores)) is not None:
                await _announce_payout(bot, payout)
        except Exception:
            logger.exception("Could not check referrals")
        await asyncio.sleep(PAYOUT_CHECK_SECONDS)
