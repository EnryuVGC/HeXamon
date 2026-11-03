from functools import lru_cache

from bot.data import catalog
from bot.game import pokedex, store

MACHINE_METHOD = "machine"
SELL_DIVISOR = 2


def move_of(number: int) -> str | None:
    machine = catalog.load("technical_machines").get(str(number))
    return machine["name"] if machine else None


def renumbered_owned(old: dict) -> dict:
    legacy = catalog.load("legacy_technical_machines")
    numbers = {machine["name"]: number for number, machine in catalog.load("technical_machines").items()}
    return {
        numbers[legacy[number]["name"]]: count
        for number, count in old.items()
        if count > 0 and number in legacy
    }


def sell_price(move_name: str, in_store: bool) -> int:
    price = store.tm_price(move_name)
    return price if in_store else price // SELL_DIVISOR


def _learnset(dex_id: str) -> list[dict]:
    learnsets = catalog.load("learnsets")
    species_id = str(pokedex.entry(int(dex_id)).get("species_id") or dex_id)
    species = learnsets.get(species_id, []) if species_id != dex_id else []
    return [*learnsets.get(dex_id, []), *species]


@lru_cache(maxsize=None)
def _sold_by_machine(move_name: str) -> bool:
    return any(
        item["move"] == move_name and item["method"] == MACHINE_METHOD
        for learnset in catalog.load("learnsets").values()
        for item in learnset
    )


@lru_cache(maxsize=None)
def learner_ids(move_name: str) -> tuple[int, ...]:
    by_machine = _sold_by_machine(move_name)
    return tuple(
        int(dex_id)
        for dex_id in catalog.load("pokedex")
        if any(
            item["move"] == move_name and (not by_machine or item["method"] == MACHINE_METHOD)
            for item in _learnset(dex_id)
        )
    )


def after_teaching(moves: list[str], new_move: str, forgotten: int | None) -> list[str]:
    if forgotten is None:
        return [*moves, new_move]
    return [new_move if index == forgotten else move for index, move in enumerate(moves)]
