from dataclasses import dataclass

from bot.game import creatures
from bot.game import ev_items as rules
from bot.game.encounters import BATTLE_IDLE_SECONDS
from bot.services.settling import apply_ev_item, settle_pending
from bot.storage.pokemon import new_id
from bot.storage.stores import Stores

USED = "used"
NO_ITEM = "no_item"
CANNOT_USE = "cannot_use"
IN_BATTLE = "in_battle"
IN_TRADE = "in_trade"
GONE = "gone"
FAILED = "failed"

USE_ATTEMPTS = 5


@dataclass
class UseResult:
    status: str
    pokemon: dict | None = None
    old_value: int = 0
    new_value: int = 0
    can_use_again: bool = False


async def owns_item(stores: Stores, trainer_id: int, item: str) -> bool:
    trainer = await stores.trainers.get(trainer_id)
    return bool(trainer) and trainer.get("items", {}).get(item, 0) > 0


async def use(stores: Stores, trainer_id: int, pokemon_id: str, item: str, stat: int) -> UseResult:
    trainer = await stores.trainers.get(trainer_id)
    if trainer is None:
        return UseResult(GONE)
    await settle_pending(stores, trainer_id, trainer)
    pokemon = None
    for _ in range(USE_ATTEMPTS):
        pokemon = await stores.pokemon.get(trainer_id, pokemon_id)
        if pokemon is None:
            return UseResult(GONE)
        evs = creatures.evs_of(pokemon)
        if not rules.can_use(evs, item, stat):
            return UseResult(CANNOT_USE, pokemon)
        after = rules.after_item(evs, item, stat)
        change = {
            "id": new_id(),
            "pokemon_id": pokemon_id,
            "item": item,
            "before": pokemon.get("evs"),
            "after": after,
        }
        if not await stores.trainers.begin_ev_item(trainer_id, change, BATTLE_IDLE_SECONDS):
            return UseResult(await _refusal(stores, trainer_id, item), pokemon)
        if await apply_ev_item(stores, trainer_id, change):
            return UseResult(USED, pokemon, evs[stat], after[stat], rules.can_use(after, item, stat))
    return UseResult(FAILED, pokemon)


async def _refusal(stores: Stores, trainer_id: int, item: str) -> str:
    if await stores.trainers.in_trade(trainer_id):
        return IN_TRADE
    if await stores.trainers.in_battle(trainer_id, BATTLE_IDLE_SECONDS):
        return IN_BATTLE
    return FAILED if await owns_item(stores, trainer_id, item) else NO_ITEM
