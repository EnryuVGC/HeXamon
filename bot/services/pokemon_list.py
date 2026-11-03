from dataclasses import dataclass

from bot.game.display import DisplayChoice
from bot.game.paging import DEFAULT_PAGE_SIZE, clamp_page, page_count
from bot.game.sorting import BY_LEVEL, SortOrder
from bot.services import battle_forms
from bot.storage.stores import Stores


@dataclass
class PokemonPage:
    page: int
    pages: int
    pokemon: list[dict]
    page_size: int = DEFAULT_PAGE_SIZE
    display: DisplayChoice = DisplayChoice()
    team_full: bool = False

    @property
    def first_number(self) -> int:
        return (self.page - 1) * self.page_size + 1


async def first_page(
    stores: Stores,
    trainer_id: int,
    excluded_ids: list[str],
    total: int,
    order: SortOrder = BY_LEVEL,
    page_size: int = DEFAULT_PAGE_SIZE,
    matching: dict | None = None,
) -> PokemonPage:
    pokemon = await stores.pokemon.page_first(trainer_id, excluded_ids, order, page_size, matching)
    pokemon = await battle_forms.overlay(stores, trainer_id, pokemon)
    return PokemonPage(1, page_count(total, page_size), pokemon, page_size)


async def turn_page(
    stores: Stores,
    trainer_id: int,
    excluded_ids: list[str],
    total: int,
    page: int,
    delta: int,
    anchor_id: str,
    order: SortOrder = BY_LEVEL,
    page_size: int = DEFAULT_PAGE_SIZE,
    matching: dict | None = None,
) -> PokemonPage:
    pages = page_count(total, page_size)
    target = clamp_page(page + delta, pages)
    anchor = await stores.pokemon.get(trainer_id, anchor_id)
    if target == 1 or anchor is None:
        return await first_page(stores, trainer_id, excluded_ids, total, order, page_size, matching)

    if target >= page:
        pokemon = await stores.pokemon.page_after(
            trainer_id, excluded_ids, order, anchor, (target - page) * page_size, page_size, matching
        )
    else:
        pokemon = await stores.pokemon.page_before(
            trainer_id, excluded_ids, order, anchor, (page - target - 1) * page_size, page_size, matching
        )
    if not pokemon:
        return await first_page(stores, trainer_id, excluded_ids, total, order, page_size, matching)
    pokemon = await battle_forms.overlay(stores, trainer_id, pokemon)
    return PokemonPage(target, pages, pokemon, page_size)
