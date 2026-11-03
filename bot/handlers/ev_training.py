from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from bot.game import ev_training as rules
from bot.handlers.journey import JourneyRequired
from bot.handlers.private import private_only
from bot.services import ev_training
from bot.services.hunting import IN_BATTLE, IN_TRADE
from bot.storage.stores import Stores
from bot.ui.keyboards import EvTrainingAction, ev_training_begin_keyboard, ev_training_zone_keyboard
from bot.ui.texts import text

router = Router()
router.message.middleware(JourneyRequired())

REFUSALS = {
    ev_training.IN_SAFARI: "ev_training.in_safari",
    IN_TRADE: "trade.locked",
    IN_BATTLE: "hunt.already_in_battle",
}


def _stat_label(stat: str) -> str:
    return text(f"hunt.ev_stats.{stat}")


def _training_text(status: ev_training.EvTrainingStatus) -> str:
    return text(
        "ev_training.training",
        region=status.region,
        stat=_stat_label(status.stat),
        hunts=status.hunts,
        limit=rules.HUNT_LIMIT,
    )


@router.message(Command("evtrain"), F.from_user)
@private_only("evtrain")
async def evtrain_command(message: Message, stores: Stores) -> None:
    trainer_id = message.from_user.id
    status = await ev_training.status_of(stores, trainer_id)
    if status.status == ev_training.TRAINING:
        await message.reply(_training_text(status))
    elif status.status == ev_training.IN_SAFARI:
        await message.reply(text("ev_training.in_safari"))
    else:
        await message.reply(
            text("ev_training.info", limit=rules.HUNT_LIMIT, fee=rules.ENTRY_FEE),
            reply_markup=ev_training_begin_keyboard(trainer_id),
        )


async def _refuse(callback: CallbackQuery, status: ev_training.EvTrainingStatus) -> None:
    if status.status == ev_training.TRAINING:
        await callback.answer()
        await callback.message.edit_text(_training_text(status))
    elif status.status == ev_training.NO_MONEY:
        await callback.answer(text("ev_training.no_money", fee=rules.ENTRY_FEE), show_alert=True)
    else:
        await callback.answer(text(REFUSALS[status.status]), show_alert=True)


@router.callback_query(EvTrainingAction.filter())
async def ev_training_pressed(callback: CallbackQuery, callback_data: EvTrainingAction, stores: Stores) -> None:
    trainer_id = callback.from_user.id
    if trainer_id != callback_data.owner_id or not isinstance(callback.message, Message):
        await callback.answer(text("common.not_your_buttons"), show_alert=True)
        return
    if not callback_data.stat:
        status = await ev_training.status_of(stores, trainer_id)
        if status.status != ev_training.OPEN:
            await _refuse(callback, status)
            return
        await callback.answer()
        await callback.message.edit_text(
            text("ev_training.zones_title", region=status.region, fee=rules.ENTRY_FEE),
            reply_markup=ev_training_zone_keyboard(trainer_id),
        )
        return
    status = await ev_training.enter(stores, trainer_id, callback_data.stat)
    if status.status != ev_training.ENTERED:
        await _refuse(callback, status)
        return
    await callback.answer()
    await callback.message.edit_text(
        text("ev_training.entered", fee=rules.ENTRY_FEE, limit=rules.HUNT_LIMIT, stat=_stat_label(status.stat))
    )
