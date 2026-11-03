from random import randint, random

from bot.game import pokedex
from bot.game.experience import STAT_NAMES

MAX_IV = 31
MELTAN = 808
ULTRA_BEASTS = frozenset({793, 794, 795, 796, 797, 798, 799, 803, 804, 805, 806})
SPECIAL_TIERS = (
    (0.007, 31, 31),
    (0.025, 27, 31),
    (0.15, 24, 30),
    (0.42, 19, 27),
    (0.82, 14, 26),
    (1.0, 9, 21),
)
EGG_TIERS = (
    (0.000001, 30, 31),
    (0.0001, 28, 30),
    (0.05, 25, 29),
    (1.0, 12, 29),
)


def _roll_wild() -> int:
    return min(randint(1, MAX_IV) + randint(0, 2), MAX_IV)


def _roll_meltan() -> int:
    return min(randint(1, MAX_IV) + randint(0, 15), MAX_IV)


def _roll_special() -> int:
    chance = random()
    for limit, low, high in SPECIAL_TIERS:
        if chance < limit:
            return randint(low, high)
    return randint(SPECIAL_TIERS[-1][1], SPECIAL_TIERS[-1][2])


def is_special(dex_id: int) -> bool:
    data = pokedex.entry(dex_id)
    return data.get("is_legendary", False) or data.get("is_mythical", False) or dex_id in ULTRA_BEASTS


def roll_egg_ivs() -> list[int]:
    chance = random()
    low, high = next((low, high) for limit, low, high in EGG_TIERS if chance < limit)
    return [randint(low, high) for _ in STAT_NAMES]


def roll_ivs(dex_id: int) -> list[int]:
    if dex_id == MELTAN:
        roll = _roll_meltan
    elif is_special(dex_id):
        roll = _roll_special
    else:
        roll = _roll_wild
    return [roll() for _ in STAT_NAMES]
