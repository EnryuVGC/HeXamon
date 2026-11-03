from dataclasses import dataclass

from bot.game import display, sorting
from bot.game.display import DisplayChoice, choice_of
from bot.game.paging import is_valid_page_size, page_size_of
from bot.services import pokemon_list
from bot.services.pokemon_list import PokemonPage
from bot.services.settling import settle_pending
from bot.storage.stores import Stores


@dataclass
class SortChoice:
    key: str
    direction: str


@dataclass
class CollectionPage:
    page: PokemonPage
    total: int
    sort: SortChoice
    display: DisplayChoice
    page_size: int


def sort_of(trainer: dict) -> SortChoice:
    saved = trainer.get("pokemon_sort", {})
    return SortChoice(
        key=saved.get("key", sorting.DEFAULT_KEY),
        direction=saved.get("direction", sorting.DEFAULT_DIRECTION),
    )


async def _load(stores: Stores, trainer_id: int) -> dict | None:
    trainer = await stores.trainers.get(trainer_id)
    if not trainer or trainer.get("first_partner_id") is None:
        return None
    await settle_pending(stores, trainer_id, trainer)
    return trainer


async def first_page(stores: Stores, trainer_id: int) -> CollectionPage | None:
    trainer = await _load(stores, trainer_id)
    if trainer is None:
        return None
    sort = sort_of(trainer)
    page = await pokemon_list.first_page(
        stores,
        trainer_id,
        [],
        trainer["pokemon_count"],
        sorting.order_for(sort.key, sort.direction),
        page_size_of(trainer),
    )
    return CollectionPage(page, trainer["pokemon_count"], sort, choice_of(trainer), page_size_of(trainer))


async def turn_page(
    stores: Stores,
    trainer_id: int,
    page: int,
    delta: int,
    anchor_id: str,
) -> CollectionPage | None:
    trainer = await _load(stores, trainer_id)
    if trainer is None:
        return None
    sort = sort_of(trainer)
    result = await pokemon_list.turn_page(
        stores,
        trainer_id,
        [],
        trainer["pokemon_count"],
        page,
        delta,
        anchor_id,
        sorting.order_for(sort.key, sort.direction),
        page_size_of(trainer),
    )
    return CollectionPage(result, trainer["pokemon_count"], sort, choice_of(trainer), page_size_of(trainer))


async def current_sort(stores: Stores, trainer_id: int) -> SortChoice | None:
    trainer = await _load(stores, trainer_id)
    return sort_of(trainer) if trainer else None


async def choose_sort(stores: Stores, trainer_id: int, key: str) -> SortChoice | None:
    if not sorting.is_valid_key(key):
        return None
    await stores.trainers.set_pokemon_sort_key(trainer_id, key)
    return await current_sort(stores, trainer_id)


async def change_direction(stores: Stores, trainer_id: int) -> SortChoice | None:
    await stores.trainers.toggle_pokemon_sort_direction(trainer_id, sorting.DEFAULT_DIRECTION, sorting.ASCENDING)
    return await current_sort(stores, trainer_id)


async def current_display(stores: Stores, trainer_id: int) -> DisplayChoice | None:
    trainer = await _load(stores, trainer_id)
    return choice_of(trainer) if trainer else None


async def choose_display(stores: Stores, trainer_id: int, key: str) -> DisplayChoice | None:
    if not display.is_valid_key(key):
        return None
    await stores.trainers.set_pokemon_display_key(trainer_id, key)
    return await current_display(stores, trainer_id)


async def toggle_numbers(stores: Stores, trainer_id: int) -> DisplayChoice | None:
    await stores.trainers.toggle_pokemon_numbers(trainer_id)
    return await current_display(stores, trainer_id)


async def current_page_size(stores: Stores, trainer_id: int) -> int | None:
    trainer = await _load(stores, trainer_id)
    return page_size_of(trainer) if trainer else None


async def choose_page_size(stores: Stores, trainer_id: int, size: int) -> int | None:
    if not is_valid_page_size(size):
        return None
    await stores.trainers.set_pokemon_page_size(trainer_id, size)
    return await current_page_size(stores, trainer_id)
