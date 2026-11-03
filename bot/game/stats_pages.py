INFO = "info"
STATS = "stats"
MOVES = "moves"
IVS = "ivs"
STATS_PAGES = (INFO, STATS, MOVES, IVS)


def is_valid_page(page: str) -> bool:
    return page in STATS_PAGES
