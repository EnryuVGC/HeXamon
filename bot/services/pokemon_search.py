from dataclasses import dataclass

from bot.game import creatures, name_search, pokedex, sorting
from bot.game.display import choice_of
from bot.game.name_search import BY_NAME, BY_SPECIES
from bot.game.paging import page_size_of
from bot.services import battle_forms, pokemon_list
from bot.services.collection import sort_of
from bot.services.pokemon_list import PokemonPage
from bot.services.settling import settle_pending
from bot.storage.stores import Stores


@dataclass
class Found:
    kind: str
    pokemon: dict | None = None
    page: PokemonPage | None = None


@dataclass
class Suggestion:
    kind: str
    name: str
    example_id: str


async def _load(stores: Stores, trainer_id: int) -> dict | None:
    trainer = await stores.trainers.get(trainer_id)
    if not trainer or trainer.get("first_partner_id") is None:
        return None
    await settle_pending(stores, trainer_id, trainer)
    return trainer


def _order(trainer: dict) -> sorting.SortOrder:
    sort = sort_of(trainer)
    return sorting.order_for(sort.key, sort.direction)


def _matching(kind: str, example: dict) -> dict:
    if kind == BY_SPECIES:
        return {"dex_id": example["dex_id"]}
    return {"name": example["name"]}


async def _found(stores: Stores, trainer: dict, trainer_id: int, kind: str, matching: dict) -> Found | None:
    total = await stores.pokemon.count_matching(trainer_id, matching)
    page = await pokemon_list.first_page(
        stores,
        trainer_id,
        [],
        total,
        _order(trainer),
        page_size_of(trainer),
        matching,
    )
    if not page.pokemon:
        return None
    if total == 1:
        return Found(kind, pokemon=page.pokemon[0])
    page.display = choice_of(trainer)
    return Found(kind, page=page)


async def _suggestion(stores: Stores, trainer_id: int, query: str) -> Suggestion | None:
    searches = {
        name_search.loose_name(name): (BY_NAME, {"name": name})
        for name in await stores.pokemon.owned_names(trainer_id)
    }
    for dex_id in await stores.pokemon.owned_dex_ids(trainer_id):
        searches[name_search.loose_name(pokedex.species_name(dex_id))] = (BY_SPECIES, {"dex_id": dex_id})

    closest = name_search.closest(query, searches)
    if closest is None:
        return None
    kind, matching = searches[closest]
    example = await stores.pokemon.first_matching(trainer_id, matching)
    if example is None:
        return None
    name = pokedex.species_name(example["dex_id"]) if kind == BY_SPECIES else creatures.shown_name(example)
    return Suggestion(kind, name, str(example["_id"]))


async def _in_form(stores: Stores, trainer: dict, trainer_id: int, form: int) -> dict | None:
    forms = await battle_forms.live_forms(stores, trainer)
    pokemon_id = next((pokemon_id for pokemon_id, live in forms.items() if live == form), None)
    pokemon = await stores.pokemon.get(trainer_id, pokemon_id) if pokemon_id else None
    return creatures.with_form(pokemon, form) if pokemon else None


async def search(stores: Stores, trainer_id: int, query: str) -> Found | Suggestion | None:
    trainer = await _load(stores, trainer_id)
    if trainer is None:
        return None
    dex_id = pokedex.dex_id_named(name_search.loose_name(query))
    if dex_id is not None:
        changed = await _in_form(stores, trainer, trainer_id, dex_id)
        if changed is not None:
            return Found(BY_SPECIES, pokemon=changed)
        found = await _found(stores, trainer, trainer_id, BY_SPECIES, {"dex_id": dex_id})
        if found is not None:
            return found
    found = await _found(stores, trainer, trainer_id, BY_NAME, {"name": name_search.typed_name(query)})
    return found or await _suggestion(stores, trainer_id, query)


async def accept_suggestion(stores: Stores, trainer_id: int, kind: str, example_id: str) -> Found | None:
    trainer = await _load(stores, trainer_id)
    example = await stores.pokemon.get(trainer_id, example_id)
    if trainer is None or example is None:
        return None
    return await _found(stores, trainer, trainer_id, kind, _matching(kind, example))


async def turn_list_page(
    stores: Stores,
    trainer_id: int,
    kind: str,
    page: int,
    delta: int,
    anchor_id: str,
) -> PokemonPage | None:
    trainer = await _load(stores, trainer_id)
    anchor = await stores.pokemon.get(trainer_id, anchor_id)
    if trainer is None or anchor is None:
        return None
    matching = _matching(kind, anchor)
    result = await pokemon_list.turn_page(
        stores,
        trainer_id,
        [],
        await stores.pokemon.count_matching(trainer_id, matching),
        page,
        delta,
        anchor_id,
        _order(trainer),
        page_size_of(trainer),
        matching,
    )
    result.display = choice_of(trainer)
    return result


async def pokemon_of(stores: Stores, trainer_id: int, pokemon_id: str) -> dict | None:
    trainer = await _load(stores, trainer_id)
    if trainer is None:
        return None
    pokemon = await stores.pokemon.get(trainer_id, pokemon_id)
    if pokemon is None:
        return None
    return (await battle_forms.overlay(stores, trainer_id, [pokemon], trainer))[0]
