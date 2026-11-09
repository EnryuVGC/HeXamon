from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.data import catalog
from bot.game import pokedex
from bot.game import store as rules
from bot.game.inventory import stone_index, stone_name
from bot.game.paging import clamp_page, page_count
from bot.ui.keyboards import (
    KEY_SELL_BUTTONS_PER_ROW,
    KEY_SELL_CANCEL,
    KEY_SELL_CONFIRM,
    KEY_SELL_LIST,
    KEY_SELL_PICK,
    KeyItemSale,
)
from bot.ui.texts import text


def _label(good: rules.Good, amount: int) -> str:
    if good.key == rules.KEY_STONE:
        return text("shop.key_stone_label")
    group = "balls" if good.is_ball else "items"
    return text(f"inventory.{group}.{good.key}.{'one' if amount == 1 else 'many'}")


def purchased_text(order) -> str:
    return text("shop.purchased", amount=order.amount, label=_label(order.good, order.amount), total=order.total)


def sold_text(order) -> str:
    return text("shop.sold", amount=order.amount, label=_label(order.good, order.amount), total=order.total)


def key_item_list_text(page: int, pages: int) -> str:
    body = text("shop.key_item_pick", price=rules.key_item_price())
    return body if pages == 1 else f"{body}\n\n{text('shop.key_item_page', page=page, pages=pages)}"


def key_item_confirm_text(stone: str) -> str:
    return text("shop.key_item_confirm", stone=stone_name(stone), price=rules.key_item_price())


def key_item_sold_text(stone: str) -> str:
    return text("shop.key_item_sold", stone=stone_name(stone), price=rules.key_item_price())


def _sale_button(label: str, owner_id: int, action: str, stone: int = -1, page: int = 1) -> InlineKeyboardButton:
    return InlineKeyboardButton(
        text=label,
        callback_data=KeyItemSale(owner_id=owner_id, action=action, stone=stone, page=page).pack(),
    )


def key_item_list_keyboard(owner_id: int, stones: list[str], page: int) -> InlineKeyboardMarkup:
    pages = page_count(len(stones), rules.KEY_ITEMS_PER_PAGE)
    page = clamp_page(page, pages)
    start = (page - 1) * rules.KEY_ITEMS_PER_PAGE
    shown = stones[start:start + rules.KEY_ITEMS_PER_PAGE]
    buttons = [
        _sale_button(stone_name(stone), owner_id, KEY_SELL_PICK, stone_index(stone), page) for stone in shown
    ]
    rows = [buttons[i:i + KEY_SELL_BUTTONS_PER_ROW] for i in range(0, len(buttons), KEY_SELL_BUTTONS_PER_ROW)]
    if pages > 1:
        turn = []
        if page > 1:
            turn.append(_sale_button(text("shop.key_item_previous"), owner_id, KEY_SELL_LIST, page=page - 1))
        if page < pages:
            turn.append(_sale_button(text("shop.key_item_next"), owner_id, KEY_SELL_LIST, page=page + 1))
        rows.append(turn)
    rows.append([_sale_button(text("shop.cancel_button"), owner_id, KEY_SELL_CANCEL)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def key_item_confirm_keyboard(owner_id: int, stone: str, page: int) -> InlineKeyboardMarkup:
    index = stone_index(stone)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _sale_button(text("shop.confirm_button"), owner_id, KEY_SELL_CONFIRM, index, page),
                _sale_button(text("shop.back_button"), owner_id, KEY_SELL_LIST, page=page),
            ]
        ]
    )


def _page(body: str) -> str:
    return f"{text('shop.header')}\n\n{body}"


def key_items_text() -> str:
    return text("shop.key_items_info", key_stone=rules.price_of(rules.KEY_STONE))


def items_text() -> str:
    return _page(
        text(
            "shop.items",
            boost=rules.price_of("boost"),
            vitamin=rules.price_of("vitamin"),
            berry=rules.price_of("berry"),
            rare_candy=rules.price_of("rare_candy"),
            key_stone=rules.price_of("key_stone"),
        )
    )


def balls_text() -> str:
    return _page(
        text(
            "shop.balls",
            regular=rules.price_of("regular balls"),
            great=rules.price_of("great balls"),
            ultra=rules.price_of("ultra balls"),
            repeat=rules.price_of("repeat balls"),
            nest=rules.price_of("nest balls"),
        )
    )


def _tm_entry(number: int) -> str:
    name = catalog.load("technical_machines")[str(number)]["name"]
    move = pokedex.move_data(name)
    return text(
        "shop.tm",
        number=number,
        price=rules.tm_price(name),
        name=pokedex.display_name(name),
        type=pokedex.display_name(move["type"]),
        symbol=text(f"display.type_symbols.{move['type']}"),
        power=move["power"],
        accuracy=move["accuracy"] if move["accuracy"] is not None else text("battle.never_misses_accuracy"),
        category=pokedex.display_name(move["damage_class"]),
    )


def tms_text(numbers: list[int]) -> str:
    entries = "\n\n".join(_tm_entry(number) for number in numbers)
    return _page(text("shop.tms", tms=entries or text("shop.tms_sold_out")))
