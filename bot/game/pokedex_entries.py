from functools import lru_cache

from bot.data import catalog
from bot.game import name_search, pokedex
from bot.game.pokedex_list import listed_dex_ids

ABOUT = "about"
BASE_STATS = "stats"
EV_YIELDS = "evs"
VIEWS = (ABOUT, BASE_STATS, EV_YIELDS)

MEGA = "mega"
BATTLE_FORMS = frozenset({MEGA, "primal", "hero"})
HIDDEN_FORMS = frozenset({"gmax"})
CATCH_LEVELS = ((25, "very_low"), (75, "low"), (150, "medium"), (225, "high"))
TOP_CATCH_LEVEL = "very_high"
MAX_NUMBER_DIGITS = 6
FIRST_FORM_WITHOUT_ARTWORK = 20000


def species_of(dex_id: int) -> int:
    return pokedex.entry(dex_id).get("species_id") or dex_id


def _shows_form(dex_id: int, words: set[str], listed: set[int]) -> bool:
    if words & HIDDEN_FORMS:
        return False
    return dex_id in listed or bool(words & BATTLE_FORMS)


@lru_cache(maxsize=None)
def _forms_by_species() -> dict[int, tuple[int, ...]]:
    listed = set(listed_dex_ids())
    forms: dict[int, list[int]] = {}
    for key, data in catalog.load("pokedex").items():
        dex_id = int(key)
        if _shows_form(dex_id, set(data["name"].split("-")), listed):
            forms.setdefault(species_of(dex_id), []).append(dex_id)
    return {species: tuple(sorted(ids)) for species, ids in forms.items()}


def forms_of(dex_id: int) -> tuple[int, ...]:
    return _forms_by_species()[species_of(dex_id)]


def _shown_form(dex_id: int) -> int:
    forms = forms_of(dex_id)
    return dex_id if dex_id in forms else forms[0]


def _known(dex_id: int) -> bool:
    return str(dex_id) in catalog.load("pokedex")


def resolve(query: str) -> int | None:
    typed = query.strip()
    if typed.isascii() and typed.isdecimal() and len(typed) <= MAX_NUMBER_DIGITS:
        number = int(typed)
        return _shown_form(number) if _known(number) else None
    exact = pokedex.dex_id_named(name_search.loose_name(typed))
    return _shown_form(exact) if exact is not None else None


def in_pokedex(dex_id: int, seen: set[int]) -> bool:
    return any(species_of(seen_id) == species_of(dex_id) for seen_id in seen)


def closest_seen(query: str, seen: set[int]) -> int | None:
    names = {
        name_search.loose_name(pokedex.species_name(form)): form
        for seen_id in seen
        for form in forms_of(seen_id)
    }
    close = name_search.closest(query, names)
    return names[close] if close else None


def base_form(dex_id: int) -> int:
    return forms_of(dex_id)[0]


def artwork_id(dex_id: int) -> int:
    return base_form(dex_id) if dex_id >= FIRST_FORM_WITHOUT_ARTWORK else dex_id


def form_words(dex_id: int) -> list[str]:
    base_words = pokedex.entry(base_form(dex_id))["name"].split("-")
    words = pokedex.entry(dex_id)["name"].split("-")
    shared = 0
    while shared < min(len(words), len(base_words)) and words[shared] == base_words[shared]:
        shared += 1
    return words[shared:]


def catch_level(dex_id: int) -> str:
    rate = pokedex.entry(dex_id)["catch_rate"] or pokedex.entry(base_form(dex_id))["catch_rate"]
    return next((level for limit, level in CATCH_LEVELS if rate <= limit), TOP_CATCH_LEVEL)


def growth_rate(dex_id: int) -> str:
    return pokedex.entry(dex_id)["growth_rate"] or pokedex.entry(base_form(dex_id))["growth_rate"]


def _regions_holding(dex_id: int) -> list[str]:
    pools = catalog.load("regional_dex")
    return [region for region in catalog.load("regions") if dex_id in pools[region.casefold()]]


def regions_found(dex_id: int) -> list[str]:
    return _regions_holding(dex_id) or _regions_holding(base_form(dex_id))
