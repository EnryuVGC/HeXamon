DEFAULT_PAGE_SIZE = 20
PAGE_SIZE_OPTIONS = (10, 15, 20, 25)
JUMP_SIZES = (5, 10, 20)


def page_count(total: int, page_size: int = DEFAULT_PAGE_SIZE) -> int:
    return max(1, (total + page_size - 1) // page_size)


def clamp_page(page: int, pages: int) -> int:
    return max(1, min(pages, page))


def available_jumps(pages: int, sizes: tuple[int, ...] = JUMP_SIZES) -> list[int]:
    return [jump for jump in sizes if pages > jump]


def can_turn(page: int, pages: int, delta: int) -> bool:
    return 1 <= page + delta <= pages


def page_size_of(trainer: dict) -> int:
    return trainer.get("pokemon_page_size", DEFAULT_PAGE_SIZE)


def is_valid_page_size(size: int) -> bool:
    return size in PAGE_SIZE_OPTIONS
