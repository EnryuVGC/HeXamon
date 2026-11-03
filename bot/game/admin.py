from dataclasses import dataclass

from bot.data import catalog
from bot.game import experience, inventory, pokedex

MONEY = "money"
BALL = "ball"
ITEM = "item"
KEY_STONE = "key_stone"
STONE = "stone"
TM = "tm"
POKEMON = "pokemon"
EGG = "egg"
EXP = "exp"

DEFAULT_POKEMON_LEVEL = 5
MAX_AMOUNT = 1000000000
MAX_EGGS = 20
ITEM_NAMES = {
    "boost": "boost",
    "boosts": "boost",
    "vitamin": "vitamin",
    "vitamins": "vitamin",
    "berry": "berry",
    "berries": "berry",
    "candy": "rare_candy",
    "candies": "rare_candy",
    "rarecandy": "rare_candy",
    "rarecandies": "rare_candy",
}
MONEY_NAMES = ("money", "dollars", "pokedollars", "pd", "cash")
KEY_STONE_NAMES = ("keystone",)
EGG_NAMES = ("egg", "eggs")
EXP_NAMES = ("exp", "xp")


@dataclass(frozen=True)
class Grant:
    kind: str
    key: str
    amount: int


def _squeezed(words: list[str]) -> str:
    return "".join(words).replace("-", "").replace("_", "").casefold()


def _amount_of(words: list[str]) -> tuple[list[str], int | None]:
    if words and words[-1].isascii() and words[-1].isdecimal():
        return words[:-1], int(words[-1])
    return words, None


def _ball_key(name: str) -> str | None:
    for ball in inventory.BALL_ORDER:
        if name in (ball, f"{ball}ball", f"{ball}balls"):
            return ball
    return None


def _stone_key(name: str) -> str | None:
    for stone in catalog.load("mega_stone_image_ids"):
        if _squeezed([stone]) == name:
            return stone
    return None


def _tm_grant(words: list[str], amount: int | None) -> Grant | None:
    if len(words) != 1 or not words[0].casefold().startswith("tm"):
        return None
    if words[0][2:].isdecimal():
        return Grant(TM, str(int(words[0][2:])), amount or 1)
    return Grant(TM, str(amount), 1) if words[0].casefold() == "tm" and amount is not None else None


def parse_grant(args: str | None) -> Grant | None:
    words, amount = _amount_of((args or "").split())
    if len(words) == 2 and words[0].casefold() == "tm" and words[1].isdecimal():
        words = ["tm" + words[1]]
    if not words or (amount is not None and not 1 <= amount <= MAX_AMOUNT):
        return None
    name = _squeezed(words)
    if name in MONEY_NAMES:
        return Grant(MONEY, MONEY, amount or 1)
    if name in KEY_STONE_NAMES:
        return Grant(KEY_STONE, KEY_STONE, 1)
    if name in EGG_NAMES:
        return Grant(EGG, EGG, amount or 1) if (amount or 1) <= MAX_EGGS else None
    if name in EXP_NAMES:
        return Grant(EXP, EXP, amount or 1)
    ball = _ball_key(name)
    if ball:
        return Grant(BALL, ball, amount or 1)
    if name in ITEM_NAMES:
        return Grant(ITEM, ITEM_NAMES[name], amount or 1)
    tm = _tm_grant(words, amount)
    if tm:
        return tm if str(int(tm.key)) in catalog.load("technical_machines") else None
    stone = _stone_key(name)
    if stone:
        return Grant(STONE, stone, 1)
    dex_id = pokedex.dex_id_named(" ".join(words).replace("-", " ").casefold())
    level = amount or DEFAULT_POKEMON_LEVEL
    if dex_id is not None and level <= experience.MAX_LEVEL:
        return Grant(POKEMON, str(dex_id), level)
    return None


def parse_target_id(args: str | None) -> int | None:
    words = (args or "").split()
    return int(words[0]) if len(words) == 1 and words[0].isascii() and words[0].isdecimal() else None
