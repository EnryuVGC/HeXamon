import random
from dataclasses import dataclass

from bot.data import catalog
from bot.game.mega_evolutions import KEY_ITEMS

LINK_PREFIX = "ref_"
TARGET_EXP = 500
INVITE_REWARD = 50
BALLS_EVERY = 5
STONE_EVERY = 12
MASTER_EVERY = 25
BALL_MIX = {"regular": 10, "great": 5, "ultra": 3}


@dataclass(frozen=True)
class Milestone:
    balls: bool = False
    tm: str | None = None
    master: bool = False
    stone: str | None = None


def link_payload(trainer_id: int) -> str:
    return f"{LINK_PREFIX}{trainer_id}"


def referrer_of_payload(payload: str | None) -> int | None:
    if not payload or not payload.startswith(LINK_PREFIX):
        return None
    referrer = payload.removeprefix(LINK_PREFIX)
    return int(referrer) if referrer.isdecimal() else None


def roll_milestone(count: int, owned_stones: list[str]) -> Milestone:
    balls = count % BALLS_EVERY == 0
    missing = [
        stone
        for stone in catalog.load("mega_stone_image_ids")
        if stone not in owned_stones and stone not in KEY_ITEMS
    ]
    return Milestone(
        balls=balls,
        tm=random.choice(list(catalog.load("technical_machines"))) if balls else None,
        master=count % MASTER_EVERY == 0,
        stone=random.choice(missing) if count % STONE_EVERY == 0 and missing else None,
    )


def reward_counters(milestone: Milestone) -> dict[str, int]:
    counters = {"money": INVITE_REWARD}
    if milestone.balls:
        counters.update({f"balls.{ball}": amount for ball, amount in BALL_MIX.items()})
    if milestone.tm:
        counters[f"tms.{milestone.tm}"] = 1
    if milestone.master:
        counters["balls.master"] = 1
    return counters
