from dataclasses import dataclass

from bot.game import pokedex_entries as rules
from bot.storage.stores import Stores


@dataclass(frozen=True)
class Suggestion:
    dex_id: int


async def _seen_by(stores: Stores, trainer_id: int) -> set[int]:
    trainer = await stores.trainers.get(trainer_id)
    return set(trainer["seen_dex"]) | set(trainer["caught_dex"]) if trainer else set()


async def search(stores: Stores, trainer_id: int, query: str) -> int | Suggestion | None:
    seen = await _seen_by(stores, trainer_id)
    dex_id = rules.resolve(query)
    if dex_id is not None and rules.in_pokedex(dex_id, seen):
        return dex_id
    close = rules.closest_seen(query, seen)
    return Suggestion(close) if close is not None else None


async def can_view(stores: Stores, trainer_id: int, dex_id: int) -> bool:
    return rules.in_pokedex(dex_id, await _seen_by(stores, trainer_id))
