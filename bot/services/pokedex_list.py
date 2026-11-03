from dataclasses import dataclass

from bot.game import pokedex_list
from bot.storage.stores import Stores


@dataclass
class PokedexPage:
    page: int
    pages: int
    first_number: int
    dex_ids: tuple[int, ...]
    seen: set[int]
    caught: set[int]


async def page_of(stores: Stores, trainer_id: int, page: int) -> PokedexPage | None:
    trainer = await stores.trainers.get(trainer_id)
    if trainer is None:
        return None
    caught = set(trainer.get("caught_dex", []))
    target = pokedex_list.clamped(page)
    return PokedexPage(
        target,
        pokedex_list.pages(),
        pokedex_list.first_number(target),
        pokedex_list.dex_ids_on(target),
        caught.union(trainer.get("seen_dex", [])),
        caught,
    )
