from dataclasses import dataclass

from bot.game import encounters, ev_training as rules
from bot.services.hunting import IN_BATTLE, IN_TRADE
from bot.storage.stores import Stores

ENTERED = "entered"
TRAINING = "training"
IN_SAFARI = "in_safari"
NO_MONEY = "no_money"
OPEN = "open"


@dataclass
class EvTrainingStatus:
    status: str
    region: str = ""
    stat: str = ""
    hunts: int = 0


def _status_of(trainer: dict) -> EvTrainingStatus:
    session = trainer.get("ev_training")
    if session:
        return EvTrainingStatus(TRAINING, session["region"].title(), session["stat"], session["hunts"])
    if trainer.get("safari"):
        return EvTrainingStatus(IN_SAFARI)
    return EvTrainingStatus(OPEN, trainer["region"].title())


async def status_of(stores: Stores, trainer_id: int) -> EvTrainingStatus:
    return _status_of(await stores.trainers.get(trainer_id))


async def enter(stores: Stores, trainer_id: int, stat: str) -> EvTrainingStatus:
    trainer = await stores.trainers.get(trainer_id)
    status = _status_of(trainer)
    if status.status != OPEN:
        return status
    session = rules.new_session(trainer["region"], stat)
    entered = await stores.trainers.enter_ev_training(
        trainer_id,
        session,
        rules.ENTRY_FEE,
        encounters.BATTLE_IDLE_SECONDS,
    )
    if entered:
        return EvTrainingStatus(ENTERED, status.region, stat)
    latest = await stores.trainers.get(trainer_id)
    status = _status_of(latest)
    if status.status != OPEN:
        return status
    if await stores.trainers.in_trade(trainer_id):
        return EvTrainingStatus(IN_TRADE)
    if latest.get("money", 0) < rules.ENTRY_FEE:
        return EvTrainingStatus(NO_MONEY)
    return EvTrainingStatus(IN_BATTLE)


async def leave(stores: Stores, trainer_id: int) -> bool:
    return await stores.trainers.leave_ev_training(trainer_id) is not None
