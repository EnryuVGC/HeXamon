from dataclasses import dataclass

from bot.data import catalog

STARTING_REGION = "kanto"
STARTING_GENERATION = "Gen 1"
STARTING_LEVEL = 5
STARTING_MONEY = 300
NO_CHOICE_PARTNER = "Pikachu"


@dataclass(frozen=True)
class Partner:
    dex_id: int
    name: str


def _partner(name: str) -> Partner:
    ids_by_name = {
        entry["name"]: int(dex_id)
        for dex_id, entry in catalog.load("pokedex").items()
    }
    return Partner(dex_id=ids_by_name[name.lower()], name=name)


def first_partners() -> list[Partner]:
    return [_partner(name) for name in catalog.load("starters")[STARTING_GENERATION]]


def no_choice_partner() -> Partner:
    return _partner(NO_CHOICE_PARTNER)


def find_first_partner(dex_id: int) -> Partner | None:
    partners = [*first_partners(), no_choice_partner()]
    return next((p for p in partners if p.dex_id == dex_id), None)
