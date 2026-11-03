from bot.data import catalog
from bot.game.paging import clamp_page, page_count

BALL_ORDER = ("regular", "great", "ultra", "level", "fast", "repeat", "nest", "net", "quick", "master", "safari")
ITEM_ORDER = ("boost", "vitamin", "berry", "rare_candy")
TMS_PER_PAGE = 20


def owned(order: tuple[str, ...], amounts: dict) -> list[tuple[str, int]]:
    return [(key, amounts[key]) for key in order if amounts.get(key, 0) > 0]


def sorted_stones(stones: list[str]) -> list[str]:
    known = list(catalog.load("mega_stone_image_ids"))
    return sorted(stones, key=lambda stone: known.index(stone) if stone in known else len(known))


def stone_name(stone: str) -> str:
    return stone.replace("-", " ")


def _stone_command(stone: str) -> str:
    return stone.casefold().replace("-", "_")


def stone_commands() -> tuple[str, ...]:
    return tuple(_stone_command(stone) for stone in catalog.load("mega_stone_image_ids"))


def stone_of_command(command: str) -> str | None:
    for stone in catalog.load("mega_stone_image_ids"):
        if _stone_command(stone) == command.casefold():
            return stone
    return None


def owned_tms(tms: dict) -> list[tuple[int, int]]:
    known = catalog.load("technical_machines")
    return sorted((int(number), count) for number, count in tms.items() if count > 0 and number in known)


def tm_pages(total: int) -> int:
    return page_count(total, TMS_PER_PAGE)


def tms_on_page(tms: list[tuple[int, int]], page: int) -> list[tuple[int, int]]:
    start = (clamp_page(page, tm_pages(len(tms))) - 1) * TMS_PER_PAGE
    return tms[start:start + TMS_PER_PAGE]
