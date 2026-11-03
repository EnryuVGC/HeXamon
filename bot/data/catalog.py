import json
from functools import lru_cache
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
ASSETS_DIR = ROOT / "assets"
FORM_IMAGES_CHANNEL = "HeXaImages"

FILES = {
    "pokedex": "pokemon/pokedex.json",
    "catch_rates": "pokemon/catch_rates.json",
    "evolutions": "pokemon/evolutions.json",
    "learnsets": "pokemon/learnsets.json",
    "form_image_posts": "pokemon/form_image_posts.json",
    "moves": "moves/moves.json",
    "technical_machines": "moves/technical_machines.json",
    "type_chart": "battle/type_chart.json",
    "natures": "battle/natures.json",
    "regions": "world/regions.json",
    "regional_dex": "world/regional_dex.json",
    "safari_encounters": "world/safari_encounters.json",
    "starters": "world/starters.json",
    "legacy_technical_machines": "moves/legacy_technical_machines.json",
    "item_prices": "items/item_prices.json",
    "mega_stone_image_ids": "items/mega_stone_image_ids.json",
    "texts": "ui/texts.json",
    "card_text_colors": "ui/card_text_colors.json",
    "card_templates": "ui/card_templates.json",
}


def _read(relative_path: str) -> Any:
    with open(DATA_DIR / relative_path, encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=None)
def load(name: str) -> Any:
    return _read(FILES[name])


def form_artwork(name: str, shiny: bool) -> str | None:
    post = load("form_image_posts").get(f"{name}{'-shiny' if shiny else ''}")
    return f"https://t.me/{FORM_IMAGES_CHANNEL}/{post}" if post else None


def card_template(number: int) -> Path:
    return ASSETS_DIR / "cards" / f"{number}.png"


def card_title() -> Path:
    return ASSETS_DIR / "cards" / "title.png"


def card_badges() -> Path:
    return ASSETS_DIR / "cards" / "badges.png"


def trainer_sprite(name: str) -> Path:
    return ASSETS_DIR / "trainers" / f"{name}.png"


def font(name: str) -> Path:
    return ASSETS_DIR / "fonts" / f"{name}.ttf"
