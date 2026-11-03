from dataclasses import dataclass
from datetime import date
from random import Random

from bot.data import catalog
from bot.game import pokedex

WEEKLY_TM_COUNT = 5
TM_PRICE_PER_POWER = 7
SELL_DIVISOR = 2
MAX_TRADE_AMOUNT = 100000
KEY_STONE = "key_stone"


@dataclass(frozen=True)
class Good:
    key: str
    field: str
    price_key: str
    names: tuple[str, ...]

    @property
    def is_ball(self) -> bool:
        return self.field.startswith("balls.")


def _ball(key: str) -> Good:
    return Good(key, f"balls.{key}", f"{key} balls", (key, f"{key}ball", f"{key}balls"))


def _item(key: str, *names: str) -> Good:
    return Good(key, f"items.{key}", key, (key.replace("_", ""), *names))


GOODS = (
    _ball("regular"),
    _ball("great"),
    _ball("ultra"),
    _ball("repeat"),
    _ball("nest"),
    _item("boost", "boosts"),
    _item("vitamin", "vitamins"),
    _item("berry", "berries"),
    _item("rare_candy", "candy", "candies", "rarecandy", "rarecandies"),
    Good(KEY_STONE, KEY_STONE, KEY_STONE, ("keystone",)),
)
_GOODS_BY_NAME = {name: good for good in GOODS for name in good.names}


def price_of(item: str) -> int:
    return catalog.load("item_prices")[item]


def sell_price_of(good: Good) -> int:
    return price_of(good.price_key) // SELL_DIVISOR


def parse_order(args: str | None) -> tuple[Good, int] | None:
    words = (args or "").casefold().split()
    has_amount = bool(words) and words[-1].isascii() and words[-1].isdecimal()
    amount = int(words[-1]) if has_amount else 1
    name_words = words[:-1] if has_amount else words
    good = _GOODS_BY_NAME.get("".join(name_words).replace("-", "").replace("_", ""))
    if good is None or not 1 <= amount <= MAX_TRADE_AMOUNT:
        return None
    if not has_amount and good.key != KEY_STONE:
        return None
    return good, amount


def tm_price(move_name: str) -> int:
    return pokedex.move_data(move_name)["power"] * TM_PRICE_PER_POWER


def _sold_tms() -> list[int]:
    return sorted(int(number) for number in catalog.load("technical_machines"))


def weekly_tms(trainer_id: int, today: date) -> list[int]:
    year, week, _ = today.isocalendar()
    return Random(f"{trainer_id}-{year}-{week}").sample(_sold_tms(), WEEKLY_TM_COUNT)


def tm_purchase(number: int, today: date) -> str:
    year, week, _ = today.isocalendar()
    return f"{year}-{week}:{number}"


def available_tms(trainer_id: int, trainer: dict, today: date) -> list[int]:
    bought = trainer.get("bought_store_tms", [])
    return [number for number in weekly_tms(trainer_id, today) if tm_purchase(number, today) not in bought]
