import random
from functools import lru_cache

from bot.data import catalog
from bot.game import creatures, pokedex
from bot.game.ivs import MELTAN, ULTRA_BEASTS

BATTLE_IDLE_SECONDS = 120
LEGENDARY = "legendary"
MYTHICAL = "mythical"
ULTRA_BEAST = "ultra_beast"
REGULAR = "regular"
LEGENDARY_ODDS = 200
MYTHICAL_ODDS = 275
ULTRA_BEAST_ODDS = 150
RARE_FORM_ODDS = 200000
FOUND_TM_ODDS = 5000
FOUND_STONE_ODDS = 25000
STONE_IMAGES_CHANNEL = "@HeXaAssets"
ALOLA = "alola"
KALOS = "kalos"
FLOETTE_ETERNAL = 10061
SILVALLY = 773
ULTRA_BEAST_RATE_IDS = ULTRA_BEASTS | {801, 802, 807}


def _tier_of(dex_id: int) -> str | None:
    data = pokedex.entry(dex_id)
    legendary, mythical = data.get("is_legendary", False), data.get("is_mythical", False)
    if dex_id in ULTRA_BEAST_RATE_IDS:
        return ULTRA_BEAST
    if legendary and not mythical:
        return LEGENDARY
    if mythical and not legendary:
        return MYTHICAL
    return REGULAR if not legendary and not mythical else None


@lru_cache(maxsize=None)
def _wild_pools(region: str) -> dict[str, tuple[int, ...]]:
    pools = {LEGENDARY: [], MYTHICAL: [], ULTRA_BEAST: [], REGULAR: []}
    for dex_id in catalog.load("regional_dex")[region]:
        tier = _tier_of(dex_id)
        if dex_id != MELTAN and tier is not None:
            pools[tier].append(dex_id)
    return {tier: tuple(pool) for tier, pool in pools.items()}


@lru_cache(maxsize=None)
def regular_spawns() -> tuple[int, ...]:
    return tuple(sorted({
        dex_id
        for region in catalog.load("regional_dex")
        for dex_id in _wild_pools(region)[REGULAR]
    }))


def regular_pool(region: str) -> tuple[int, ...]:
    return _wild_pools(region)[REGULAR]


def _one_in(odds: int) -> bool:
    return random.randint(1, odds) == 1


def roll_found_tm() -> str | None:
    if not _one_in(FOUND_TM_ODDS):
        return None
    return random.choice(list(catalog.load("technical_machines")))


def roll_found_stone(owned: list[str]) -> str | None:
    if not _one_in(FOUND_STONE_ODDS):
        return None
    missing = [stone for stone in catalog.load("mega_stone_image_ids") if stone not in owned]
    return random.choice(missing) if missing else None


def stone_image_id(stone: str) -> int:
    return catalog.load("mega_stone_image_ids")[stone]


def _roll_pool(region: str) -> tuple[int, ...]:
    pools = _wild_pools(region)
    if _one_in(LEGENDARY_ODDS):
        pool = pools[LEGENDARY]
    elif _one_in(MYTHICAL_ODDS):
        pool = pools[MYTHICAL]
    elif region == ALOLA and _one_in(ULTRA_BEAST_ODDS):
        pool = pools[ULTRA_BEAST]
    elif region == ALOLA and _one_in(RARE_FORM_ODDS):
        pool = (MELTAN,)
    elif region == KALOS and _one_in(RARE_FORM_ODDS):
        pool = (FLOETTE_ETERNAL,)
    else:
        pool = pools[REGULAR]
    return pool or pools[REGULAR]


@lru_cache(maxsize=None)
def _silvally_forms() -> tuple[int, ...]:
    return tuple(int(dex_id) for dex_id, data in catalog.load("pokedex").items() if data.get("species_id") == SILVALLY)


def roll_wild(region: str) -> dict:
    dex_id = random.choice(_roll_pool(region))
    if dex_id == SILVALLY:
        dex_id = random.choice(_silvally_forms())
    level_range = pokedex.entry(dex_id)["wild_range"]
    level = random.randint(level_range["min"], level_range["max"])
    return creatures.with_shiny_roll(creatures.new_pokemon(dex_id, level))


def battle_copy(pokemon: dict) -> dict:
    return {
        "dex_id": pokemon["dex_id"],
        "level": pokemon["level"],
        "nature": pokemon["nature"],
        "ivs": pokemon["ivs"],
        "evs": creatures.evs_of(pokemon),
        "moves": pokemon["moves"],
        "nickname": pokemon["nickname"],
        "shiny": pokemon.get("shiny", False),
    }


def new_encounter(encounter_id: str, wild: dict, lead: dict) -> dict:
    return {
        "id": encounter_id,
        "state": "found",
        "turn": 0,
        "wild": wild,
        "wild_hp": creatures.stats_of(wild)["hp"],
        "player": battle_copy(lead),
        "player_id": str(lead["_id"]),
        "player_hp": creatures.stats_of(lead)["hp"],
        "team_hp": {},
        "participants": [str(lead["_id"])],
    }
