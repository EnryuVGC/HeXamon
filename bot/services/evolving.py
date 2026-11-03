import random
from dataclasses import dataclass

from bot.game import evolution as rules
from bot.game.encounters import BATTLE_IDLE_SECONDS
from bot.services.settling import RewardGain, apply_evolution, settle_pending
from bot.storage.pokemon import new_id
from bot.storage.stores import Stores

EVOLVED = "evolved"
READY = "ready"
NEVER = "never"
NOT_YET = "not_yet"
IN_BATTLE = "in_battle"
IN_TRADE = "in_trade"
GONE = "gone"
FAILED = "failed"


@dataclass
class EvolveResult:
    status: str
    pokemon: dict | None = None
    new_dex_id: int | None = None


def readiness(pokemon: dict, region: str) -> str:
    if not rules.evolutions_of(pokemon["dex_id"], region):
        return NEVER
    return READY if rules.ready_evolutions(pokemon, region) else NOT_YET


async def newly_ready(stores: Stores, gains: list[RewardGain]) -> list[dict]:
    ready = []
    for gain in gains:
        if gain.new_level == gain.old_level:
            continue
        trainer = await stores.trainers.get(gain.pokemon["trainer_id"])
        grown = {**gain.pokemon, "level": gain.new_level}
        if trainer and readiness(grown, trainer["region"]) == READY and readiness(gain.pokemon, trainer["region"]) != READY:
            ready.append(grown)
    return ready


async def status_of(stores: Stores, trainer_id: int, pokemon: dict) -> str:
    trainer = await stores.trainers.get(trainer_id)
    return readiness(pokemon, trainer["region"])


async def pokemon_of(stores: Stores, trainer_id: int, pokemon_id: str) -> dict | None:
    return await stores.pokemon.get(trainer_id, pokemon_id)


async def evolve(stores: Stores, trainer_id: int, pokemon_id: str, dex_id: int) -> EvolveResult:
    trainer = await stores.trainers.get(trainer_id)
    if trainer is None:
        return EvolveResult(GONE)
    await settle_pending(stores, trainer_id, trainer)
    pokemon = await stores.pokemon.get(trainer_id, pokemon_id)
    if pokemon is None or pokemon["dex_id"] != dex_id:
        return EvolveResult(GONE)
    options = rules.ready_evolutions(pokemon, trainer["region"])
    if not options:
        return EvolveResult(readiness(pokemon, trainer["region"]), pokemon)

    chosen = random.choice(options)
    evolving = {
        "id": new_id(),
        "pokemon_id": pokemon_id,
        "from_dex_id": pokemon["dex_id"],
        "to_dex_id": chosen.dex_id,
    }
    if not await stores.trainers.begin_evolution(trainer_id, evolving, BATTLE_IDLE_SECONDS):
        return EvolveResult(await _refusal(stores, trainer_id), pokemon)
    if not await apply_evolution(stores, trainer_id, evolving):
        return EvolveResult(FAILED, pokemon)
    return EvolveResult(EVOLVED, pokemon, chosen.dex_id)


async def _refusal(stores: Stores, trainer_id: int) -> str:
    if await stores.trainers.in_trade(trainer_id):
        return IN_TRADE
    if await stores.trainers.in_battle(trainer_id, BATTLE_IDLE_SECONDS):
        return IN_BATTLE
    return FAILED
