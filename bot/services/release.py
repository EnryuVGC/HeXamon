from dataclasses import dataclass

from bot.game.encounters import BATTLE_IDLE_SECONDS
from bot.game.teams import team_numbers
from bot.services.settling import settle_pending
from bot.storage.stores import Stores

RELEASED = "released"
IN_BATTLE = "in_battle"
IN_TRADE = "in_trade"
LAST_POKEMON = "last_pokemon"
GONE = "gone"
HATCHED = "hatched"


@dataclass
class ReleaseResult:
    status: str
    pokemon: dict | None = None


async def can_lose_one(stores: Stores, trainer_id: int) -> bool:
    return await stores.trainers.has_spare_pokemon(trainer_id)


async def pokemon_to_release(stores: Stores, trainer_id: int, pokemon_id: str) -> dict | None:
    await settle_pending(stores, trainer_id)
    return await stores.pokemon.get(trainer_id, pokemon_id)


async def ask(stores: Stores, trainer_id: int, pokemon_id: str, message_id: int, previous_body: str) -> None:
    await stores.trainers.set_release_prompt(trainer_id, pokemon_id, message_id, previous_body)


async def previous_body(stores: Stores, trainer_id: int, pokemon_id: str, message_id: int) -> str | None:
    return await stores.trainers.take_release_prompt(trainer_id, pokemon_id, message_id)


async def release(stores: Stores, trainer_id: int, pokemon_id: str, message_id: int) -> ReleaseResult:
    pokemon = await pokemon_to_release(stores, trainer_id, pokemon_id)
    if pokemon is None:
        return ReleaseResult(GONE)
    if pokemon.get("egg"):
        return ReleaseResult(HATCHED)
    started = await stores.trainers.begin_release(
        trainer_id,
        pokemon_id,
        list(team_numbers()),
        BATTLE_IDLE_SECONDS,
    )
    if not started:
        if await stores.trainers.in_trade(trainer_id):
            return ReleaseResult(IN_TRADE)
        in_battle = await stores.trainers.in_battle(trainer_id, BATTLE_IDLE_SECONDS)
        return ReleaseResult(IN_BATTLE if in_battle else LAST_POKEMON)

    await stores.trainers.drop_found_encounter(trainer_id, pokemon_id)
    deleted = await stores.pokemon.delete(trainer_id, pokemon_id)
    await stores.trainers.finish_release(trainer_id, pokemon_id, counted=deleted is not None)
    if deleted is None:
        return ReleaseResult(GONE)
    await stores.trainers.take_release_prompt(trainer_id, pokemon_id, message_id)
    return ReleaseResult(RELEASED, deleted)
