from dataclasses import dataclass

from bot.game import creatures, pokedex
from bot.game.catching import catch_rate_of

OPTIONS = (
    "none",
    "level",
    "iv",
    "ev",
    "nature",
    "type",
    "type_symbol",
    "catch",
    "hp",
    "attack",
    "defense",
    "sp_attack",
    "sp_defense",
    "speed",
    "total",
)
FIRST_STAT_OPTION = 8
DEFAULT_KEY = "level"
STAT_BY_OPTION = {
    "hp": "hp",
    "attack": "attack",
    "defense": "defense",
    "sp_attack": "special_attack",
    "sp_defense": "special_defense",
    "speed": "speed",
}


@dataclass(frozen=True)
class DisplayChoice:
    key: str = DEFAULT_KEY
    numbered: bool = True


def choice_of(trainer: dict) -> DisplayChoice:
    saved = trainer.get("pokemon_display", {})
    return DisplayChoice(saved.get("key", DEFAULT_KEY), saved.get("numbered", True))


def is_valid_key(key: str) -> bool:
    return key in OPTIONS


def number_value(pokemon: dict, key: str) -> int:
    if key == "level":
        return pokemon["level"]
    if key == "iv":
        return sum(pokemon["ivs"])
    if key == "ev":
        return sum(creatures.evs_of(pokemon))
    if key == "catch":
        return catch_rate_of(pokemon["dex_id"])
    stats = creatures.stats_of(pokemon)
    if key == "total":
        return sum(stats.values())
    return stats[STAT_BY_OPTION[key]]


def raw_types(pokemon: dict) -> list[str]:
    return pokedex.entry(creatures.form_id(pokemon))["types"]
