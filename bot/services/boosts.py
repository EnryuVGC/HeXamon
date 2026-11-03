from dataclasses import dataclass

from bot.game import boosts as rules
from bot.game.encounters import BATTLE_IDLE_SECONDS
from bot.services.ev_items import owns_item
from bot.services.settling import apply_boost, settle_pending
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
class BoostResult:
    status: str
    pokemon: dict | None = None
    old_value: int = 0
    new_value: int = 0


async def owns_boost(stores: Stores, trainer_id: int) -> bool:
    return await owns_item(stores, trainer_id, rules.BOOST)


async def use(stores: Stores, trainer_id: int, pokemon_id: str, stat: int) -> BoostResult:
    trainer = await stores.trainers.get(trainer_id)
    if trainer is None:
        return BoostResult(GONE)
    await settle_pending(stores, trainer_id, trainer)
    pokemon = None
    for _ in range(USE_ATTEMPTS):
        pokemon = await stores.pokemon.get(trainer_id, pokemon_id)
        if pokemon is None:
            return BoostResult(GONE)
        if not rules.can_boost(pokemon, stat):
            return BoostResult(CANNOT_USE, pokemon)
        boost = {"id": new_id(), "pokemon_id": pokemon_id, "stat": stat}
        if not await stores.trainers.begin_boost(trainer_id, boost, BATTLE_IDLE_SECONDS):
            return BoostResult(await _refusal(stores, trainer_id), pokemon)
        if await apply_boost(stores, trainer_id, boost):
            old_value = pokemon["ivs"][stat]
            return BoostResult(USED, pokemon, old_value, rules.after_boost(pokemon["ivs"], stat)[stat])
    return BoostResult(FAILED, pokemon)


async def _refusal(stores: Stores, trainer_id: int) -> str:
    if await stores.trainers.in_trade(trainer_id):
        return IN_TRADE
    if await stores.trainers.in_battle(trainer_id, BATTLE_IDLE_SECONDS):
        return IN_BATTLE
    return FAILED if await owns_boost(stores, trainer_id) else NO_ITEM
