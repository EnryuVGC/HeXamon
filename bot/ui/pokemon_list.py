from html import escape
from typing import Callable

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.game import creatures, display as display_rules
from bot.game import pokedex
from bot.game.display import DisplayChoice
from bot.game.paging import available_jumps, can_turn
from bot.ui.texts import text

NUMBER_BUTTONS_PER_ROW = 4


class PokemonListPage(CallbackData, prefix="plist"):
    owner_id: int
    screen: str
    page: int
    delta: int
    anchor: str


class PokemonListIndicator(CallbackData, prefix="plisti"):
    owner_id: int


def detail(pokemon: dict, key: str) -> str:
    if key == "none":
        return ""
    if key == "nature":
        return pokemon["nature"]
    if key == "type":
        names = pokedex.type_names(creatures.form_id(pokemon))
        return text("battle.type_separator").join(names)
    if key == "type_symbol":
        symbols = [text(f"display.type_symbols.{name}") for name in display_rules.raw_types(pokemon)]
        return text("display.type_symbol_separator").join(symbols)
    return text(f"display.values.{key}", value=display_rules.number_value(pokemon, key))


def badge_list(pokemon: dict) -> list[str]:
    badges = [text("pokemon_list.shiny_badge")] if pokemon.get("shiny") else []
    if pokemon.get("egg"):
        badges.append(text("pokemon_list.egg_badge"))
    return badges


def badges(pokemon: dict) -> str:
    return "".join(badge_list(pokemon))


def line(number: int, pokemon: dict, display: DisplayChoice, force_numbers: bool = False) -> str:
    name = escape(creatures.shown_name(pokemon))
    value = detail(pokemon, display.key)
    body = text("pokemon_list.with_detail", name=name, detail=value) if value else text("pokemon_list.name", name=name)
    body += badges(pokemon)
    if display.numbered or force_numbers:
        return text("pokemon_list.numbered", number=number, body=body)
    return body


def lines(
    pokemon: list[dict],
    display: DisplayChoice,
    first_number: int = 1,
    force_numbers: bool = False,
) -> str:
    return "\n".join(
        line(number, entry, display, force_numbers)
        for number, entry in enumerate(pokemon, start=first_number)
    )


def _nav_button(label_key: str, owner_id: int, screen: str, page, delta: int) -> InlineKeyboardButton:
    anchor = page.pokemon[0]
    return InlineKeyboardButton(
        text=text(f"pokemon_list.{label_key}"),
        callback_data=PokemonListPage(
            owner_id=owner_id,
            screen=screen,
            page=page.page,
            delta=delta,
            anchor=str(anchor["_id"]),
        ).pack(),
    )


def page_rows(
    page: int,
    pages: int,
    jumps: list[int],
    indicator: InlineKeyboardButton,
    button: Callable[[str, int], InlineKeyboardButton],
) -> list[list[InlineKeyboardButton]]:
    if pages <= 1:
        return []
    arrows = [
        *([button("previous_button", -1)] if can_turn(page, pages, -1) else []),
        indicator,
        *([button("next_button", 1)] if can_turn(page, pages, 1) else []),
    ]
    rows = [arrows]
    for jump in jumps:
        row = [
            *([button(f"back_{jump}_button", -jump)] if can_turn(page, pages, -jump) else []),
            *([button(f"forward_{jump}_button", jump)] if can_turn(page, pages, jump) else []),
        ]
        if row:
            rows.append(row)
    return rows


def nav_rows(owner_id: int, screen: str, page) -> list[list[InlineKeyboardButton]]:
    return page_rows(
        page.page,
        page.pages,
        available_jumps(page.pages),
        InlineKeyboardButton(
            text=text("pokemon_list.page_indicator", page=page.page, pages=page.pages),
            callback_data=PokemonListIndicator(owner_id=owner_id).pack(),
        ),
        lambda label_key, delta: _nav_button(label_key, owner_id, screen, page, delta),
    )


def keyboard(
    owner_id: int,
    screen: str,
    page,
    pick_callback: Callable[[dict], str] | None = None,
    extra_rows: list[list[InlineKeyboardButton]] | None = None,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if pick_callback is not None:
        for number, pokemon in enumerate(page.pokemon, start=1):
            builder.button(text=str(number), callback_data=pick_callback(pokemon))
        builder.adjust(NUMBER_BUTTONS_PER_ROW)
    for row in [*nav_rows(owner_id, screen, page), *(extra_rows or [])]:
        builder.row(*row)
    return builder.as_markup()
