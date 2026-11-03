from functools import lru_cache

from bot.data import catalog
from bot.game.paging import clamp_page, page_count

PAGE_SIZE = 25
JUMP_SIZES = (5, 10)
ALWAYS_LISTED_FORMS = frozenset({"totem", "cap"})


def _obtainable_dex_ids() -> set[int]:
    evolved = [data["evolution"] for data in catalog.load("evolutions").values()]
    pools = [*catalog.load("regional_dex").values(), *catalog.load("safari_encounters").values(), *evolved]
    return {dex_id for pool in pools for dex_id in pool}


@lru_cache(maxsize=None)
def listed_dex_ids() -> tuple[int, ...]:
    obtainable = _obtainable_dex_ids()
    listed = [
        (data.get("species_id") or int(dex_id), int(dex_id))
        for dex_id, data in catalog.load("pokedex").items()
        if data["is_default"] or int(dex_id) in obtainable or not ALWAYS_LISTED_FORMS.isdisjoint(data["name"].split("-"))
    ]
    return tuple(dex_id for _, dex_id in sorted(listed))


def pages() -> int:
    return page_count(len(listed_dex_ids()), PAGE_SIZE)


def clamped(page: int) -> int:
    return clamp_page(page, pages())


def first_number(page: int) -> int:
    return (page - 1) * PAGE_SIZE + 1


def dex_ids_on(page: int) -> tuple[int, ...]:
    start = first_number(page) - 1
    return listed_dex_ids()[start:start + PAGE_SIZE]
