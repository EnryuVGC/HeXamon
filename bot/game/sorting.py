from dataclasses import dataclass

ASCENDING = "asc"
DESCENDING = "desc"
FIRST_STAT_OPTION = 9


@dataclass(frozen=True)
class SortOption:
    key: str
    field: str


OPTIONS = (
    SortOption("caught", "_id"),
    SortOption("dex", "dex_id"),
    SortOption("level", "level"),
    SortOption("iv", "iv_total"),
    SortOption("ev", "ev_total"),
    SortOption("name", "name"),
    SortOption("nature", "nature"),
    SortOption("type", "type"),
    SortOption("catch", "catch_rate"),
    SortOption("hp", "stats.0"),
    SortOption("attack", "stats.1"),
    SortOption("defense", "stats.2"),
    SortOption("sp_attack", "stats.3"),
    SortOption("sp_defense", "stats.4"),
    SortOption("speed", "stats.5"),
    SortOption("total", "stat_total"),
)
DEFAULT_KEY = "level"
DEFAULT_DIRECTION = DESCENDING


@dataclass(frozen=True)
class SortOrder:
    field: str
    descending: bool


BY_LEVEL = SortOrder("level", True)


def option_for(key: str) -> SortOption:
    return next(option for option in OPTIONS if option.key == key)


def is_valid_key(key: str) -> bool:
    return any(option.key == key for option in OPTIONS)


def order_for(key: str, direction: str) -> SortOrder:
    return SortOrder(option_for(key).field, direction == DESCENDING)
