from dataclasses import dataclass

from bot.game import safari
from bot.game import travel as rules
from bot.services.hunting import today_key
from bot.storage.stores import Stores

TRAVELED = "traveled"
ALREADY_HERE = "already_here"
LOCKED = "locked"
GONE = "gone"
IN_SAFARI = "in_safari"
IN_EV_TRAINING = "in_ev_training"


@dataclass
class TravelMenu:
    regions: list[str]
    current: str
    has_more: bool
    in_safari: bool = False
    in_ev_training: bool = False


@dataclass
class TravelResult:
    status: str
    region: str = ""


async def menu_of(stores: Stores, trainer_id: int) -> TravelMenu | None:
    trainer = await stores.trainers.get(trainer_id)
    if trainer is None:
        return None
    regions = rules.unlocked_regions(trainer.get("exp_points", 0))
    in_safari = safari.is_active(trainer.get("safari"), today_key())
    return TravelMenu(regions, trainer["region"].title(), len(regions) < len(rules.all_regions()), in_safari, "ev_training" in trainer)


async def go(stores: Stores, trainer_id: int, region_index: int) -> TravelResult:
    regions = rules.all_regions()
    trainer = await stores.trainers.get(trainer_id)
    if trainer is None or not 0 <= region_index < len(regions):
        return TravelResult(GONE)
    region = regions[region_index]
    key = rules.region_key(region)
    today = today_key()
    if safari.is_active(trainer.get("safari"), today):
        return TravelResult(IN_SAFARI, region)
    if "ev_training" in trainer:
        return TravelResult(IN_EV_TRAINING, region)
    if trainer["region"] == key:
        return TravelResult(ALREADY_HERE, region)
    if not await stores.trainers.set_region(trainer_id, key, rules.minimum_exp(region_index), today):
        return TravelResult(LOCKED, region)
    return TravelResult(TRAVELED, region)
