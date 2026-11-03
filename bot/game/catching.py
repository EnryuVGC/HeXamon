import random
from dataclasses import dataclass

from bot.data import catalog
from bot.game import pokedex
from bot.game.mega_evolutions import mega_evolutions

THROWABLE_BALLS = ("regular", "great", "ultra", "level", "fast", "repeat", "nest", "net", "quick", "master")
FIXED_BALL_BONUS = {"regular": 1.0, "great": 1.5, "ultra": 2.0, "master": 255.0}
FAST_BALL_MIN_SPEED = 100
FAST_BALL_SPECIES = {81, 88, 114}
NET_BALL_TYPES = {"water", "bug"}
STARTING_BALLS = {"regular": 10, "great": 5, "ultra": 5}
SHAKE_CHECKS = 4
MAX_STARS = 3
MAX_CATCH_VALUE = 255
DEFAULT_CATCH_RATE = 45
NO_STATUS_BONUS = 2.4
HELD_STONE_ODDS = 1000
LEGENDARY_FLEE_PERCENT = (15, 35)
MYTHICAL_FLEE_PERCENT = (5, 25)
REGULAR_FLEE_PERCENT = (0, 15)
MASTER_BALL_DROP_ODDS = 25000
BALL_DROP_ODDS = 100
BALL_DROP_AMOUNT = (1, 3)
BALL_DROP_POOL = ("level", "fast", "repeat", "nest", "net", "quick")
ITEM_DROP_ODDS = 100
ITEM_DROP_AMOUNT = (1, 3)
ITEM_DROPS = ("rare_candy", "vitamin")
TM_DROP_ODDS = 500
TM_DROP = "tm"
MONEY_GIFT_ODDS = 500
MONEY_GIFT_AMOUNT = (100, 500)
MONEY_GIFT = "money"
BALL_DROP = "balls"
MASTER_BALL_DROP = "master"


@dataclass(frozen=True)
class FleeDrop:
    kind: str
    field: str
    amount: int
    ball: str = ""
    tm: str = ""


def catch_rate_of(dex_id: int) -> int:
    return catalog.load("catch_rates").get(str(dex_id), DEFAULT_CATCH_RATE)


def _level_ball_bonus(player_level: int, wild_level: int) -> float:
    if player_level >= wild_level * 4:
        return 8.0
    if player_level >= wild_level * 2:
        return 4.0
    return 2.0 if player_level > wild_level else 1.0


def ball_bonus(ball: str, wild: dict, player_level: int, turn: int, caught_dex: list[int]) -> float:
    if ball in FIXED_BALL_BONUS:
        return FIXED_BALL_BONUS[ball]
    dex_id = wild["dex_id"]
    data = pokedex.entry(dex_id)
    if ball == "level":
        return _level_ball_bonus(player_level, wild["level"])
    if ball == "fast":
        return 4.0 if data["stats"]["speed"] >= FAST_BALL_MIN_SPEED or dex_id in FAST_BALL_SPECIES else 1.0
    if ball == "repeat":
        return 3.5 if dex_id in caught_dex else 1.0
    if ball == "nest":
        return max(1.0, (41 - wild["level"]) / 10)
    if ball == "net":
        return 3.5 if NET_BALL_TYPES.intersection(data["types"]) else 1.0
    return 5.0 if turn == 0 else 1.0


def roll_catch(max_hp: int, hp: int, catch_rate: int, bonus: float) -> tuple[int, bool]:
    rate = catch_rate * NO_STATUS_BONUS * bonus
    value = (3 * max_hp - 2 * hp) * rate / (3 * max_hp)
    if value >= MAX_CATCH_VALUE:
        return MAX_STARS, True

    threshold = int(65535 * (value / MAX_CATCH_VALUE) ** 0.25)
    shakes = 0
    for _ in range(SHAKE_CHECKS):
        if random.randint(0, 65535) > threshold:
            break
        shakes += 1
    return min(shakes, MAX_STARS), shakes == SHAKE_CHECKS


def _one_in(odds: int) -> bool:
    return random.randint(1, odds) == 1


def rolls_flee(dex_id: int) -> bool:
    data = pokedex.entry(dex_id)
    if data.get("is_legendary", False):
        low, high = LEGENDARY_FLEE_PERCENT
    elif data.get("is_mythical", False):
        low, high = MYTHICAL_FLEE_PERCENT
    else:
        low, high = REGULAR_FLEE_PERCENT
    return random.randint(1, 100) <= random.randint(low, high)


def _master_drop() -> FleeDrop:
    return FleeDrop(MASTER_BALL_DROP, "balls.master", 1, "master")


def _tm_drop() -> FleeDrop:
    tm = random.choice(list(catalog.load("technical_machines")))
    return FleeDrop(TM_DROP, f"tms.{tm}", 1, tm=tm)


def _ball_drop() -> FleeDrop:
    ball = random.choice(BALL_DROP_POOL)
    return FleeDrop(BALL_DROP, f"balls.{ball}", random.randint(*BALL_DROP_AMOUNT), ball)


def _item_drop() -> FleeDrop:
    item = random.choice(ITEM_DROPS)
    return FleeDrop(item, f"items.{item}", random.randint(*ITEM_DROP_AMOUNT))


def _money_drop() -> FleeDrop:
    return FleeDrop(MONEY_GIFT, "money", random.randint(*MONEY_GIFT_AMOUNT))


def roll_flee_drop() -> FleeDrop | None:
    if _one_in(MASTER_BALL_DROP_ODDS):
        return _master_drop()
    if _one_in(TM_DROP_ODDS):
        return _tm_drop()
    if _one_in(BALL_DROP_ODDS):
        return _ball_drop()
    if _one_in(ITEM_DROP_ODDS):
        return _item_drop()
    if _one_in(MONEY_GIFT_ODDS):
        return _money_drop()
    return None


def roll_held_stone(dex_id: int, owned: list[str]) -> str | None:
    stones = [
        data.get("stone_item", stone)
        for stone, data in mega_evolutions.items()
        if data["pokemon_id"] == dex_id
    ]
    missing = [stone for stone in stones if stone not in owned]
    if not missing or random.randint(1, HELD_STONE_ODDS) != 1:
        return None
    return random.choice(missing)
