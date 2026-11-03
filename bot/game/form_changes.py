from dataclasses import dataclass

from bot.game.mega_evolutions import mega_evolutions


@dataclass(frozen=True)
class FormOption:
    item: str
    form_id: int


def usable_items(key_stone: bool, stones: list[str]) -> list[str]:
    return stones if key_stone else []


def options_for(dex_id: int, items: list[str]) -> list[FormOption]:
    return [
        FormOption(data.get("stone_item", stone), data["mega_id"])
        for stone, data in mega_evolutions.items()
        if data["pokemon_id"] == dex_id and data.get("stone_item", stone) in items
    ]


def option_with(options: list[FormOption], form_id: int) -> FormOption | None:
    return next((option for option in options if option.form_id == form_id), None)
