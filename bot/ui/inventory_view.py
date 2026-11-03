from bot.data import catalog
from bot.game import inventory as rules
from bot.game import pokedex
from bot.game.mega_evolutions import KEY_ITEMS, MEGA_STONE_NAMES
from bot.ui.texts import text


def _lines(group: str, amounts: list[tuple[str, int]]) -> str:
    return "\n".join(
        text(
            "inventory.line",
            name=text(f"inventory.{group}.{key}.{'one' if count == 1 else 'many'}"),
            count=count,
        )
        for key, count in amounts
    )


def main_text(inventory) -> str:
    parts = [
        text("inventory.money", money=inventory.money),
        _lines("balls", inventory.balls),
        _lines("items", inventory.items),
        text("inventory.eggs", count=inventory.eggs) if inventory.eggs else "",
    ]
    return "\n\n".join(part for part in parts if part)


def key_items_text(inventory) -> str:
    state = text("inventory.equipped") if inventory.key_stone else text("inventory.not_equipped")
    parts = [text("inventory.key_stone", state=state)]
    if inventory.mega_stones:
        parts.append("\n".join(rules.stone_name(stone) for stone in inventory.mega_stones))
    return "\n\n".join(parts)


def stone_card(stone: str) -> str:
    pokemon, form = MEGA_STONE_NAMES[stone]
    key = "inventory.key_item_card" if stone in KEY_ITEMS else "inventory.mega_stone_card"
    return text(key, name=rules.stone_name(stone), pokemon=pokemon, form=form)


def _tm_line(number: int, count: int) -> str:
    move = catalog.load("technical_machines")[str(number)]["name"]
    line = text("inventory.tm_line", number=number, name=pokedex.display_name(move))
    return text("inventory.tm_count", line=line, count=count) if count > 1 else line


def tms_text(inventory, page: int) -> str:
    shown = rules.tms_on_page(inventory.tms, page)
    if not shown:
        return text("inventory.no_tms")
    return text("inventory.tms", tms="\n".join(_tm_line(number, count) for number, count in shown))
