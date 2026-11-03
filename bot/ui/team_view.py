from html import escape

from bot.game import creatures
from bot.game.display import DisplayChoice
from bot.game.teams import TEAM_SIZE
from bot.ui import pokemon_list
from bot.ui.texts import text


def team_lines(members: list[dict], display: DisplayChoice) -> str:
    lines = [pokemon_list.line(number, pokemon, display) for number, pokemon in enumerate(members, start=1)]
    for number in range(len(members) + 1, TEAM_SIZE + 1):
        if display.numbered:
            lines.append(text("team.empty_slot", number=number))
        else:
            lines.append(text("team.empty_slot_unnumbered"))
    return "\n".join(lines)


def team_text(number: int, members: list[dict], display: DisplayChoice) -> str:
    return f"{text('team.title', number=number)}\n\n{team_lines(members, display)}"


def editor_text(members: list[dict], display: DisplayChoice) -> str:
    if not members:
        return text("team.editor_empty")
    return pokemon_list.lines(members, display)


def add_text(pokemon: list[dict], display: DisplayChoice, team_full: bool = False) -> str:
    title = text("team.add_full_title") if team_full else text("team.add_title")
    return f"{title}\n\n{pokemon_list.lines(pokemon, display, force_numbers=True)}"


def replace_text(incoming: dict, members: list[dict], display: DisplayChoice) -> str:
    title = text("team.replace_title", name=escape(creatures.shown_name(incoming)))
    return f"{title}\n\n{pokemon_list.lines(members, display, force_numbers=True)}"


def remove_text(members: list[dict], display: DisplayChoice) -> str:
    return f"{text('team.remove_title')}\n\n{pokemon_list.lines(members, display, force_numbers=True)}"


def order_text(members: list[dict], display: DisplayChoice) -> str:
    return f"{text('team.order_title')}\n\n{pokemon_list.lines(members, display, force_numbers=True)}"
