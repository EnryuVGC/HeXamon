from dataclasses import dataclass

from bot.game import teams as team_rules
from bot.game.display import DisplayChoice, choice_of
from bot.game.encounters import BATTLE_IDLE_SECONDS
from bot.game.paging import page_size_of
from bot.game.sorting import BY_LEVEL
from bot.services import battle_forms, pokemon_list
from bot.services.pokemon_list import PokemonPage
from bot.services.settling import settle_pending
from bot.storage.stores import Stores

UPDATED = "updated"
NEEDS_PARTNER = "needs_partner"
TEAM_FULL = "team_full"
NOT_ENOUGH = "not_enough"
STALE = "stale"


@dataclass
class TeamView:
    number: int
    member_ids: list[str]
    members: list[dict]
    display: DisplayChoice


@dataclass
class ReplacePrompt:
    incoming: dict
    team: TeamView


async def _load(stores: Stores, trainer_id: int) -> dict | None:
    trainer = await stores.trainers.get(trainer_id)
    if not trainer or trainer.get("first_partner_id") is None:
        return None
    await settle_pending(stores, trainer_id, trainer)
    return trainer


def _active_ids(trainer: dict) -> list[str]:
    return trainer["teams"][str(trainer["active_team"])]


async def _view(
    stores: Stores,
    trainer: dict,
    trainer_id: int,
    number: int,
    member_ids: list[str],
) -> TeamView:
    found = await stores.pokemon.by_ids(trainer_id, member_ids)
    members = [found[member_id] for member_id in member_ids if member_id in found]
    members = await battle_forms.overlay(stores, trainer_id, members, trainer)
    return TeamView(number=number, member_ids=member_ids, members=members, display=choice_of(trainer))


async def in_battle(stores: Stores, trainer_id: int) -> bool:
    return await stores.trainers.in_battle(trainer_id, BATTLE_IDLE_SECONDS)


async def in_trade(stores: Stores, trainer_id: int) -> bool:
    return await stores.trainers.in_trade(trainer_id)


async def active_team(stores: Stores, trainer_id: int) -> TeamView | None:
    trainer = await _load(stores, trainer_id)
    if trainer is None:
        return None
    return await _view(stores, trainer, trainer_id, trainer["active_team"], _active_ids(trainer))


async def select_team(stores: Stores, trainer_id: int, number: int) -> TeamView | None:
    trainer = await _load(stores, trainer_id)
    if trainer is None or number not in team_rules.team_numbers():
        return None
    if not await stores.trainers.select_team(trainer_id, number, BATTLE_IDLE_SECONDS):
        return await _view(stores, trainer, trainer_id, trainer["active_team"], _active_ids(trainer))
    return await _view(stores, trainer, trainer_id, number, trainer["teams"][str(number)])


def _eligible_total(trainer: dict) -> int:
    return max(0, trainer["pokemon_count"] - len(_active_ids(trainer)))


def _is_full(trainer: dict) -> bool:
    return len(_active_ids(trainer)) >= team_rules.TEAM_SIZE


async def first_add_page(stores: Stores, trainer_id: int) -> PokemonPage | None:
    trainer = await _load(stores, trainer_id)
    if trainer is None:
        return None
    page = await pokemon_list.first_page(
        stores,
        trainer_id,
        _active_ids(trainer),
        _eligible_total(trainer),
        BY_LEVEL,
        page_size_of(trainer),
    )
    page.display = choice_of(trainer)
    page.team_full = _is_full(trainer)
    return page


async def turn_add_page(
    stores: Stores,
    trainer_id: int,
    page: int,
    delta: int,
    anchor_id: str,
) -> PokemonPage | None:
    trainer = await _load(stores, trainer_id)
    if trainer is None:
        return None
    result = await pokemon_list.turn_page(
        stores,
        trainer_id,
        _active_ids(trainer),
        _eligible_total(trainer),
        page,
        delta,
        anchor_id,
        BY_LEVEL,
        page_size_of(trainer),
    )
    result.display = choice_of(trainer)
    result.team_full = _is_full(trainer)
    return result


async def replace_prompt(stores: Stores, trainer_id: int, pokemon_id: str) -> ReplacePrompt | None:
    trainer = await _load(stores, trainer_id)
    if trainer is None or not _is_full(trainer) or pokemon_id in _active_ids(trainer):
        return None
    incoming = await stores.pokemon.get(trainer_id, pokemon_id)
    if incoming is None:
        return None
    team = await _view(stores, trainer, trainer_id, trainer["active_team"], _active_ids(trainer))
    return ReplacePrompt(incoming, team)


async def replace_member(stores: Stores, trainer_id: int, pokemon_id: str, slot: int) -> str:
    trainer = await _load(stores, trainer_id)
    if trainer is None or await stores.pokemon.get(trainer_id, pokemon_id) is None:
        return NEEDS_PARTNER
    members = _active_ids(trainer)
    if not 0 <= slot < len(members) or pokemon_id in members:
        return STALE
    replaced = list(members)
    replaced[slot] = pokemon_id
    changed = await stores.trainers.replace_team(
        trainer_id, trainer["active_team"], members, replaced, BATTLE_IDLE_SECONDS
    )
    return UPDATED if changed else STALE


async def add_member(stores: Stores, trainer_id: int, pokemon_id: str) -> str:
    trainer = await _load(stores, trainer_id)
    if trainer is None or await stores.pokemon.get(trainer_id, pokemon_id) is None:
        return NEEDS_PARTNER
    added = await stores.trainers.add_team_member(
        trainer_id, trainer["active_team"], pokemon_id, team_rules.TEAM_SIZE, BATTLE_IDLE_SECONDS
    )
    return UPDATED if added else TEAM_FULL


async def remove_member(stores: Stores, trainer_id: int, pokemon_id: str) -> str:
    trainer = await _load(stores, trainer_id)
    if trainer is None:
        return NEEDS_PARTNER
    removed = await stores.trainers.remove_team_member(
        trainer_id, trainer["active_team"], pokemon_id, BATTLE_IDLE_SECONDS
    )
    return UPDATED if removed else STALE


async def swap_members(stores: Stores, trainer_id: int, first: int, second: int) -> str:
    trainer = await _load(stores, trainer_id)
    if trainer is None:
        return NEEDS_PARTNER
    members = _active_ids(trainer)
    if not (0 <= first < len(members) and 0 <= second < len(members)) or first == second:
        return STALE
    changed = await stores.trainers.replace_team(
        trainer_id, trainer["active_team"], members, team_rules.swapped(members, first, second), BATTLE_IDLE_SECONDS
    )
    return UPDATED if changed else STALE


async def randomize(stores: Stores, trainer_id: int) -> str:
    trainer = await _load(stores, trainer_id)
    if trainer is None:
        return NEEDS_PARTNER
    members = _active_ids(trainer)
    if len(members) < 2:
        return NOT_ENOUGH
    changed = await stores.trainers.replace_team(
        trainer_id, trainer["active_team"], members, team_rules.shuffled(members), BATTLE_IDLE_SECONDS
    )
    return UPDATED if changed else STALE


async def save_as(stores: Stores, trainer_id: int, target: int) -> str:
    trainer = await _load(stores, trainer_id)
    if trainer is None or target not in team_rules.team_numbers():
        return NEEDS_PARTNER
    saved = await stores.trainers.save_team_as(
        trainer_id, trainer["active_team"], _active_ids(trainer), target, BATTLE_IDLE_SECONDS
    )
    return UPDATED if saved else STALE
