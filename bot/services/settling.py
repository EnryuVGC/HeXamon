from dataclasses import dataclass

from bot.game import boosts, creatures, experience, pokedex
from bot.storage.pokemon import new_id
from bot.storage.stores import Stores

PROGRESS_ATTEMPTS = 5


@dataclass
class RewardGain:
    pokemon: dict
    old_level: int
    new_level: int
    learned: list[str]
    waiting: list[str]
    fields: dict


def queued_rewards(defeated: dict, participant_ids: list[str], winner_id: str | None) -> list[dict]:
    return [
        {**reward, "id": new_id()}
        for reward in experience.battle_rewards(defeated, participant_ids, winner_id)
    ]


async def apply_reward(stores: Stores, trainer_id: int, reward: dict) -> RewardGain | None:
    for _ in range(PROGRESS_ATTEMPTS):
        pokemon = await stores.pokemon.get(trainer_id, reward["pokemon_id"])
        if pokemon is None or reward["id"] in pokemon.get("applied_rewards", []):
            return None
        fields = creatures.after_reward(pokemon, reward["exp"], reward["evs"])
        applied = await stores.pokemon.apply_progress(
            trainer_id,
            reward["pokemon_id"],
            reward["id"],
            pokemon.get("exp"),
            pokemon.get("evs"),
            fields,
        )
        if applied:
            learned = [move for move in fields["moves"] if move not in pokemon["moves"]]
            gained = pokedex.moves_gained_between(pokemon["dex_id"], pokemon["level"], fields["level"])
            waiting = [move for move in gained if move not in fields["moves"]]
            return RewardGain(pokemon, pokemon["level"], fields["level"], learned, waiting, fields)
    return None


async def apply_teaching(stores: Stores, trainer_id: int, teaching: dict) -> bool:
    pokemon_id = teaching["pokemon_id"]
    applied = await stores.pokemon.replace_moves(trainer_id, pokemon_id, teaching["before"], teaching["after"])
    if not applied:
        pokemon = await stores.pokemon.get(trainer_id, pokemon_id)
        applied = pokemon is not None and pokemon["moves"] == teaching["after"]
    if applied:
        await stores.trainers.finish_teaching(trainer_id, teaching["id"])
    else:
        await stores.trainers.refund_teaching(trainer_id, teaching["id"], teaching["tm"])
    return applied


async def apply_evolution(stores: Stores, trainer_id: int, evolving: dict) -> bool:
    pokemon = await stores.pokemon.get(trainer_id, evolving["pokemon_id"])
    done = pokemon is not None and pokemon["dex_id"] == evolving["to_dex_id"]
    if pokemon is not None and pokemon["dex_id"] == evolving["from_dex_id"]:
        fields = creatures.after_evolution(pokemon, evolving["to_dex_id"])
        done = await stores.pokemon.evolve(trainer_id, evolving["pokemon_id"], evolving["from_dex_id"], fields)
    if done:
        await stores.trainers.finish_evolution(trainer_id, evolving["id"], evolving["to_dex_id"])
    else:
        await stores.trainers.drop_evolution(trainer_id, evolving["id"])
    return done


async def apply_ev_item(stores: Stores, trainer_id: int, change: dict) -> bool:
    pokemon = await stores.pokemon.get(trainer_id, change["pokemon_id"])
    done = pokemon is not None and creatures.evs_of(pokemon) == change["after"]
    if pokemon is not None and not done:
        fields = creatures.after_ev_change(pokemon, change["after"])
        done = await stores.pokemon.set_evs(trainer_id, change["pokemon_id"], change["before"], fields)
    if done:
        await stores.trainers.finish_ev_item(trainer_id, change["id"])
    else:
        await stores.trainers.refund_ev_item(trainer_id, change["id"], change["item"])
    return done


async def apply_boost(stores: Stores, trainer_id: int, boost: dict) -> bool:
    pokemon_id, stat = boost["pokemon_id"], boost["stat"]
    pokemon = await stores.pokemon.get(trainer_id, pokemon_id)
    done = pokemon is not None and pokemon.get("boosts", {}).get(str(stat)) == boost["id"]
    if pokemon is not None and not done and boosts.can_boost(pokemon, stat):
        fields = creatures.with_ivs(pokemon, boosts.after_boost(pokemon["ivs"], stat))
        done = await stores.pokemon.apply_boost(trainer_id, pokemon_id, boost["id"], stat, pokemon["ivs"], fields)
    if done:
        await stores.trainers.finish_boost(trainer_id, boost["id"])
    else:
        await stores.trainers.refund_boost(trainer_id, boost["id"])
    return done


async def apply_gift(stores: Stores, trainer_id: int, gift: dict) -> None:
    await stores.trainers.receive_gift(gift)
    await stores.trainers.finish_gift(trainer_id, gift["id"])


async def settle_pending(stores: Stores, trainer_id: int, trainer: dict | None = None) -> list[RewardGain]:
    trainer = trainer or await stores.trainers.get(trainer_id)
    if not trainer:
        return []
    for document in trainer.get("pending_pokemon", []):
        await stores.pokemon.insert_if_missing(document)
        await stores.trainers.clear_pending(trainer_id, document["_id"])
    for pokemon_id in trainer.get("pending_releases", []):
        await stores.pokemon.delete(trainer_id, pokemon_id)
        await stores.trainers.finish_release(trainer_id, pokemon_id, counted=True)
    for teaching in trainer.get("pending_teachings", []):
        await apply_teaching(stores, trainer_id, teaching)
    for evolving in trainer.get("pending_evolutions", []):
        await apply_evolution(stores, trainer_id, evolving)
    for change in trainer.get("pending_ev_items", []):
        await apply_ev_item(stores, trainer_id, change)
    for boost in trainer.get("pending_boosts", []):
        await apply_boost(stores, trainer_id, boost)
    for gift in trainer.get("pending_gifts", []):
        await apply_gift(stores, trainer_id, gift)
    gains = []
    for reward in trainer.get("pending_rewards", []):
        gain = await apply_reward(stores, trainer_id, reward)
        if gain is not None:
            gains.append(gain)
        await stores.trainers.clear_pending_reward(trainer_id, reward["id"])
    return gains
