from dataclasses import dataclass

from bot.game import inventory as rules
from bot.storage.stores import Stores


@dataclass
class Inventory:
    money: int
    balls: list[tuple[str, int]]
    items: list[tuple[str, int]]
    key_stone: bool
    mega_stones: list[str]
    tms: list[tuple[int, int]]
    eggs: int


async def inventory_of(stores: Stores, trainer_id: int) -> Inventory | None:
    trainer = await stores.trainers.get(trainer_id)
    if trainer is None:
        return None
    return Inventory(
        money=trainer.get("money", 0),
        balls=rules.owned(rules.BALL_ORDER, trainer.get("balls", {})),
        items=rules.owned(rules.ITEM_ORDER, trainer.get("items", {})),
        key_stone=trainer.get("key_stone", False),
        mega_stones=rules.sorted_stones(trainer.get("mega_stones", [])),
        tms=rules.owned_tms(trainer.get("tms", {})),
        eggs=len(trainer.get("eggs", [])),
    )
