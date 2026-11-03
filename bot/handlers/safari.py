from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.game import safari as rules
from bot.handlers.journey import JourneyRequired
from bot.services import ev_training, safari
from bot.services.hunting import IN_BATTLE, IN_TRADE
from bot.storage.stores import Stores
from bot.ui.texts import text

router = Router()
router.message.middleware(JourneyRequired())


def _status_line(status: safari.SafariStatus) -> str | None:
    if status.status == safari.ALREADY_INSIDE:
        return text(
            "safari.inside",
            region=status.region,
            hunts=status.hunts,
            limit=rules.HUNT_LIMIT,
            balls=status.balls,
        )
    if status.status == safari.ALREADY_PLAYED:
        return text("safari.already_played")
    if status.status == safari.IN_EV_TRAINING:
        return text("ev_training.in_training_short")
    return None


@router.message(Command("safari"), F.from_user)
async def safari_command(message: Message, stores: Stores) -> None:
    info = text("safari.info", balls=rules.STARTING_BALLS, limit=rules.HUNT_LIMIT, fee=rules.ENTRY_FEE)
    status_line = _status_line(await safari.status_of(stores, message.from_user.id))
    await message.reply(f"{info}\n\n{status_line}" if status_line else info)


@router.message(Command("enter"), F.from_user)
async def enter_command(message: Message, stores: Stores) -> None:
    result = await safari.enter(stores, message.from_user.id)
    if result.status == safari.ENTERED:
        await message.reply(text("safari.welcome", region=result.region, fee=rules.ENTRY_FEE))
    elif result.status == safari.NO_MONEY:
        await message.reply(text("safari.no_money", fee=rules.ENTRY_FEE))
    elif result.status == IN_TRADE:
        await message.reply(text("trade.locked"))
    elif result.status == IN_BATTLE:
        await message.reply(text("hunt.already_in_battle"))
    else:
        await message.reply(_status_line(result))


@router.message(Command("exit"), F.from_user)
async def exit_command(message: Message, stores: Stores) -> None:
    region = await safari.leave(stores, message.from_user.id)
    if region:
        await message.reply(text("safari.exited", region=region))
    elif await ev_training.leave(stores, message.from_user.id):
        await message.reply(text("ev_training.finished"))
    else:
        await message.reply(text("safari.not_inside"))
