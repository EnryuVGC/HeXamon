from functools import lru_cache

from bot.data import catalog

FALLBACK_MOVE = "tackle"
MAX_MOVES = 4
MULTI_WORD_SPECIES = (
    "nidoran-f", "nidoran-m", "mr-mime", "ho-oh", "mime-jr", "porygon-z", "type-null",
    "jangmo-o", "hakamo-o", "kommo-o", "tapu-koko", "tapu-lele", "tapu-bulu", "tapu-fini", "mr-rime",
    "great-tusk", "scream-tail", "brute-bonnet", "flutter-mane", "slither-wing", "sandy-shocks",
    "iron-treads", "iron-bundle", "iron-hands", "iron-jugulis", "iron-moth", "iron-thorns",
    "wo-chien", "chien-pao", "ting-lu", "chi-yu", "roaring-moon", "iron-valiant", "walking-wake",
    "iron-leaves", "gouging-fire", "raging-bolt", "iron-boulder", "iron-crown",
)


def entry(dex_id: int) -> dict:
    return catalog.load("pokedex")[str(dex_id)]


def display_name(raw_name: str) -> str:
    return raw_name.replace("-", " ").title()


def plain_name(dex_id: int) -> str:
    return display_name(entry(dex_id)["name"])


def _species_and_form(raw_name: str) -> tuple[str, str]:
    for species in MULTI_WORD_SPECIES:
        if raw_name == species or raw_name.startswith(f"{species}-"):
            return species, raw_name.removeprefix(species).removeprefix("-")
    species, _, form = raw_name.partition("-")
    return species, form


def base_species_name(dex_id: int) -> str:
    return display_name(_species_and_form(entry(dex_id)["name"])[0])


def species_name(dex_id: int) -> str:
    species, form = _species_and_form(entry(dex_id)["name"])
    return f"{display_name(species)} [{display_name(form)}]" if form else display_name(species)


def form_label(dex_id: int) -> str:
    return display_name(_species_and_form(entry(dex_id)["name"])[1])


def with_form_label(name: str, dex_id: int) -> str:
    return f"{name} [{form_label(dex_id)}]"


@lru_cache(maxsize=None)
def _dex_ids_by_name() -> dict:
    return {
        display_name(data["name"]).casefold(): int(dex_id)
        for dex_id, data in catalog.load("pokedex").items()
    }


def dex_id_named(name: str) -> int | None:
    return _dex_ids_by_name().get(name)


def type_names(dex_id: int) -> list[str]:
    return [display_name(type_name) for type_name in entry(dex_id)["types"]]


@lru_cache(maxsize=None)
def _moves_by_name() -> dict:
    return {move["name"]: move for move in catalog.load("moves")}


def move_data(name: str) -> dict:
    return _moves_by_name()[name]


def type_multiplier(move_type: str, defender_dex_id: int) -> float:
    chart = catalog.load("type_chart")[move_type]
    multiplier = 1.0
    for defender_type in entry(defender_dex_id)["types"]:
        multiplier *= chart[defender_type]
    return multiplier


def _level_up_items(dex_id: int) -> list[dict]:
    learnsets = catalog.load("learnsets")
    species_id = entry(dex_id).get("species_id") or dex_id
    learnset = learnsets.get(str(dex_id)) or learnsets.get(str(species_id)) or []
    return [item for item in learnset if item["method"] == "level-up"]


def learnable_moves(dex_id: int, level: int) -> list[str]:
    moves = _moves_by_name()
    names = [
        item["move"]
        for item in _level_up_items(dex_id)
        if item["level_learned_at"] <= level
        and moves.get(item["move"], {}).get("power")
    ]
    return list(dict.fromkeys(names)) or [FALLBACK_MOVE]


def moves_gained_between(dex_id: int, old_level: int, new_level: int) -> list[str]:
    moves = _moves_by_name()
    gained = [
        item
        for item in _level_up_items(dex_id)
        if old_level < item["level_learned_at"] <= new_level
        and moves.get(item["move"], {}).get("power")
    ]
    gained.sort(key=lambda item: item["level_learned_at"])
    return list(dict.fromkeys(item["move"] for item in gained))
