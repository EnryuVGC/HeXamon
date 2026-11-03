from bot.game import display as display_rules
from bot.game.sorting import DESCENDING, FIRST_STAT_OPTION, OPTIONS
from bot.ui import pokemon_list
from bot.ui.texts import text


def _label(key: str) -> str:
    return text(f"sort.options.{key}")


def _option_lines(start: int, end: int) -> str:
    return "\n".join(
        text("sort.option_line", number=index + 1, label=_label(OPTIONS[index].key))
        for index in range(start, end)
    )


def sort_text(sort) -> str:
    direction = "descending" if sort.direction == DESCENDING else "ascending"
    return text(
        "sort.menu",
        general=_option_lines(0, FIRST_STAT_OPTION),
        stats=_option_lines(FIRST_STAT_OPTION, len(OPTIONS)),
        current=_label(sort.key),
        direction=text(f"sort.{direction}"),
    )


def collection_text(collection) -> str:
    arrow = "arrow_down" if collection.sort.direction == DESCENDING else "arrow_up"
    return text(
        "sort.collection",
        pokemon=pokemon_list.lines(collection.page.pokemon, collection.display, collection.page.first_number),
        total=collection.total,
        sort=_label(collection.sort.key),
        arrow=text(f"sort.{arrow}"),
        display=text(f"display.options.{collection.display.key}"),
        page_size=collection.page_size,
    )


def _display_lines(start: int, end: int) -> str:
    return "\n".join(
        text(
            "display.option_line",
            number=index + 1,
            label=text(f"display.options.{display_rules.OPTIONS[index]}"),
        )
        for index in range(start, end)
    )


def display_text(display) -> str:
    return text(
        "display.menu",
        general=_display_lines(0, display_rules.FIRST_STAT_OPTION),
        stats=_display_lines(display_rules.FIRST_STAT_OPTION, len(display_rules.OPTIONS)),
        current=text(f"display.options.{display.key}"),
        numbering=text("display.yes") if display.numbered else text("display.no"),
    )
