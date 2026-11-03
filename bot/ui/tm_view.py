from html import escape

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.game import creatures, pokedex
from bot.ui import pokemon_list
from bot.ui.keyboards import (
    TM_BACK,
    TM_BUY,
    TM_CANCEL,
    TM_CONFIRM_SELL,
    TM_FORGET,
    TM_LEARNERS_BACK,
    TM_PICK,
    TM_SELL,
    TM_SCREEN_PREFIX,
    TM_USE,
    TmAction,
)
from bot.ui.texts import text

FORGET_BUTTONS_PER_ROW = 2


def move_text(name: str) -> str:
    move = pokedex.move_data(name)
    accuracy = move["accuracy"] if move["accuracy"] is not None else text("battle.never_misses_accuracy")
    return text(
        "stats.move",
        name=pokedex.display_name(name),
        type=pokedex.display_name(move["type"]),
        symbol=text(f"display.type_symbols.{move['type']}"),
        power=move["power"],
        accuracy=accuracy,
        category=pokedex.display_name(move["damage_class"]),
    )


def _offer(card) -> str:
    if card.owned and card.in_store:
        return text("tm.buy_or_sell", price=card.buy_price)
    if card.owned:
        return text("tm.sell_offer", price=card.sell_price)
    if card.in_store:
        return text("tm.buy_offer", price=card.buy_price)
    return text("tm.not_available")


def card_text(card) -> str:
    return text("tm.card", number=card.number, move=move_text(card.move), offer=_offer(card))


def _button(key: str, owner_id: int, number: int, action: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(
        text=text(f"tm.{key}"),
        callback_data=TmAction(owner_id=owner_id, number=number, action=action).pack(),
    )


def card_keyboard(owner_id: int, card) -> InlineKeyboardMarkup | None:
    rows = []
    if card.owned:
        rows.append(
            [
                _button("use_button", owner_id, card.number, TM_USE),
                _button("sell_button", owner_id, card.number, TM_SELL),
            ]
        )
    if card.in_store:
        rows.append([_button("buy_button", owner_id, card.number, TM_BUY)])
    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None


def sell_confirm_keyboard(owner_id: int, number: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _button("confirm_button", owner_id, number, TM_CONFIRM_SELL),
                _button("cancel_button", owner_id, number, TM_CANCEL),
            ]
        ]
    )


def learners_text(move: str, page) -> str:
    return text(
        "pokemon_picker.list",
        pokemon=pokemon_list.lines(page.pokemon, page.display, force_numbers=True),
        question=text("tm.which_pokemon", move=pokedex.display_name(move)),
    )


def learners_keyboard(owner_id: int, number: int, page) -> InlineKeyboardMarkup:
    return pokemon_list.keyboard(
        owner_id,
        f"{TM_SCREEN_PREFIX}{number}",
        page,
        pick_callback=lambda pokemon: TmAction(
            owner_id=owner_id,
            number=number,
            action=TM_PICK,
            pokemon_id=str(pokemon["_id"]),
        ).pack(),
        extra_rows=[[_button("back_button", owner_id, number, TM_BACK)]],
    )


def forget_text(pokemon: dict, move: str) -> str:
    known = "\n".join(
        text("tm.known_move", number=number, move=move_text(name))
        for number, name in enumerate(pokemon["moves"], start=1)
    )
    return text(
        "tm.forget_prompt",
        level=pokemon["level"],
        name=escape(creatures.shown_name(pokemon)),
        move=pokedex.display_name(move),
        moves=known,
    )


def forget_keyboard(owner_id: int, number: int, pokemon: dict) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for slot in range(len(pokemon["moves"])):
        builder.button(
            text=str(slot + 1),
            callback_data=TmAction(
                owner_id=owner_id,
                number=number,
                action=TM_FORGET,
                pokemon_id=str(pokemon["_id"]),
                slot=slot,
            ),
        )
    builder.adjust(FORGET_BUTTONS_PER_ROW)
    builder.row(_button("back_button", owner_id, number, TM_LEARNERS_BACK))
    return builder.as_markup()


def taught_text(result) -> str:
    name = escape(creatures.shown_name(result.pokemon))
    move = pokedex.display_name(result.move)
    if result.forgotten is None:
        return text("tm.learned", name=name, move=move)
    return text("tm.learned_forgot", name=name, move=move, forgotten=pokedex.display_name(result.forgotten))
