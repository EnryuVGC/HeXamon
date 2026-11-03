from difflib import get_close_matches
from typing import Collection

BY_SPECIES = "ss"
BY_NAME = "sn"
SEARCH_KINDS = (BY_SPECIES, BY_NAME)
CLOSE_MATCH_CUTOFF = 0.7
SCREEN_SEPARATOR = "."


def list_screen(kind: str, command_code: str) -> str:
    return f"{kind}{SCREEN_SEPARATOR}{command_code}"


def parse_list_screen(screen: str) -> tuple[str, str] | None:
    kind, _, command_code = screen.partition(SCREEN_SEPARATOR)
    return (kind, command_code) if kind in SEARCH_KINDS and command_code else None


def typed_name(raw: str) -> str:
    return " ".join(raw.split()).casefold()


def loose_name(raw: str) -> str:
    return typed_name(raw.replace("-", " ").replace("[", "").replace("]", ""))


def closest(query: str, names: Collection[str]) -> str | None:
    wanted = loose_name(query)
    if not wanted:
        return None
    extended = sorted(name for name in names if name.startswith(wanted))
    if extended:
        return extended[0]
    close = get_close_matches(wanted, names, n=1, cutoff=CLOSE_MATCH_CUTOFF)
    return close[0] if close else None
