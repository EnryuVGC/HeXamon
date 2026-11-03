from bot.data import catalog
from bot.game import pokedex
from bot.game import store as rules
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
