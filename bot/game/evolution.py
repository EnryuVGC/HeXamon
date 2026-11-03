from dataclasses import dataclass
from functools import lru_cache

from bot.data import catalog
from bot.game import pokedex

LEVELS_AFTER_PREVIOUS_FORM = 20
REGIONAL_TAGS = ("alola", "galar", "hisui")
REGION_LOCKED = {900: "hisui"}
REGIONAL_BRANCHES = {(123, "hisui"): 900, (217, "hisui"): 10272}


@dataclass(frozen=True)
class Evolution:
    dex_id: int
    level: int


@lru_cache(maxsize=None)
def _previous_forms() -> dict[int, list[int]]:
    previous = {}
    for dex_id, data in catalog.load("evolutions").items():
        for target in data["evolution"]:
            previous.setdefault(target, []).append(int(dex_id))
    return previous


def _minimum_level(dex_id: int) -> int | None:
    level = catalog.load("evolutions").get(str(dex_id), {}).get("minimum_level")
    return int(level) if level else None


def _has_regional_tag(dex_id: int) -> bool:
    return any(tag in pokedex.entry(dex_id)["name"] for tag in REGIONAL_TAGS)


def _is_for_regional_form(dex_id: int, target: int) -> bool:
    if _has_regional_tag(dex_id):
        return False
    return any(_has_regional_tag(form) for form in _previous_forms().get(target, []))


def _targets_of(dex_id: int) -> list[int]:
    data = catalog.load("evolutions").get(str(dex_id))
    targets = data["evolution"] if data else []
    return [target for target in targets if not _is_for_regional_form(dex_id, target)]


@lru_cache(maxsize=None)
def _required_level(dex_id: int, target: int) -> int:
    levels = [_minimum_level(target), *(_minimum_level(other) for other in _targets_of(dex_id))]
    known = [level for level in levels if level is not None]
    if known:
        return known[0] if _minimum_level(target) is not None else min(known)
    return _reached_at(dex_id) + LEVELS_AFTER_PREVIOUS_FORM


@lru_cache(maxsize=None)
def _reached_at(dex_id: int) -> int:
    minimum = _minimum_level(dex_id)
    if minimum is not None:
        return minimum
    previous = _previous_forms().get(dex_id)
    return min(_required_level(form, dex_id) for form in previous) if previous else 0


def _for_region(dex_id: int, targets: list[int], region: str) -> list[int]:
    forced = REGIONAL_BRANCHES.get((dex_id, region))
    if forced is not None:
        return [forced]
    available = [target for target in targets if REGION_LOCKED.get(target, region) == region]
    if region in REGIONAL_TAGS:
        regional = [target for target in available if region in pokedex.entry(target)["name"]]
        if regional:
            return regional
    return [target for target in available if not _has_regional_tag(target)] or available or targets


def evolutions_of(dex_id: int, region: str) -> list[Evolution]:
    targets = _targets_of(dex_id)
    if not targets:
        return []
    return [Evolution(target, _required_level(dex_id, target)) for target in _for_region(dex_id, targets, region.lower())]


def ready_evolutions(pokemon: dict, region: str) -> list[Evolution]:
    return [evolution for evolution in evolutions_of(pokemon["dex_id"], region) if pokemon["level"] >= evolution.level]
