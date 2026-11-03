from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.game.name_search import list_screen
from bot.ui import pokemon_list
from bot.ui.texts import text


class PokemonPick(CallbackData, prefix="ppick"):
    owner_id: int
    command_code: str
    pokemon_id: str


class PokemonSuggestion(CallbackData, prefix="psugg"):
    owner_id: int
    command_code: str
    kind: str
    example_id: str
    accepted: bool


def list_text(command_name: str, page) -> str:
    return text(
        "pokemon_picker.list",
        pokemon=pokemon_list.lines(page.pokemon, page.display, force_numbers=True),
        question=text(f"pokemon_picker.questions.{command_name}"),
    )


def list_keyboard(owner_id: int, command_code: str, kind: str, page) -> InlineKeyboardMarkup:
    return pokemon_list.keyboard(
        owner_id,
        list_screen(kind, command_code),
        page,
        pick_callback=lambda pokemon: PokemonPick(
            owner_id=owner_id,
            command_code=command_code,
            pokemon_id=str(pokemon["_id"]),
        ).pack(),
    )


def suggestion_keyboard(owner_id: int, command_code: str, kind: str, example_id: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for label_key, accepted in (("pokemon_picker.yes_button", True), ("pokemon_picker.no_button", False)):
        builder.button(
            text=text(label_key),
            callback_data=PokemonSuggestion(
                owner_id=owner_id,
                command_code=command_code,
                kind=kind,
                example_id=example_id,
                accepted=accepted,
            ),
        )
    builder.adjust(2)
    return builder.as_markup()
