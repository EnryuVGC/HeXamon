import random
from datetime import date, datetime, timedelta, timezone

from bot.game.mega_evolutions import KEY_ITEMS

NUMBER_COUNT = 5
HIGHEST_NUMBER = 30
ENTRY_FEE = 10
MULTIPLIER_FEE = 10
MAX_ENTRIES = 5
MULTIPLIERS = (2, 3, 4, 5)
STARTING_JACKPOT = 1000
DRAW_TIMEZONE = timezone(timedelta(hours=5, minutes=30))
JACKPOT_MATCH = 5
BALLS_MATCH = 4
ITEMS_MATCH = 3
PRIZE_BALLS = ("level", "fast", "net", "quick")
PRIZE_BALL_AMOUNT = 10
PRIZE_ITEMS = ("rare_candy", "vitamin")
PICKS_SEPARATOR = "."
NO_PICKS = "-"


def draw_day(now: datetime) -> str:
    return now.astimezone(DRAW_TIMEZONE).date().isoformat()


def next_day(day: str) -> str:
    return (date.fromisoformat(day) + timedelta(days=1)).isoformat()


def seconds_until_draw(now: datetime) -> int:
    local = now.astimezone(DRAW_TIMEZONE)
    midnight = datetime.combine(local.date() + timedelta(days=1), datetime.min.time(), DRAW_TIMEZONE)
    return max(int((midnight - local).total_seconds()), 0)


def encode_picks(picks: list[int]) -> str:
    return PICKS_SEPARATOR.join(map(str, picks)) or NO_PICKS


def decode_picks(raw: str) -> list[int]:
    return [int(number) for number in raw.split(PICKS_SEPARATOR) if number.isdecimal()]


def toggle_pick(picks: list[int], number: int) -> list[int] | None:
    if number in picks:
        return [pick for pick in picks if pick != number]
    if len(picks) >= NUMBER_COUNT:
        return None
    return [*picks, number]


def roll_numbers() -> list[int]:
    return random.sample(range(1, HIGHEST_NUMBER + 1), NUMBER_COUNT)


def roll_winning_numbers() -> list[int]:
    return sorted(roll_numbers())


def roll_multiplier() -> int:
    return random.choice(MULTIPLIERS)


def is_complete(picks: list[int]) -> bool:
    return (
        len(picks) == NUMBER_COUNT
        and len(set(picks)) == NUMBER_COUNT
        and all(1 <= number <= HIGHEST_NUMBER for number in picks)
    )


def entry_cost(multiplied: bool) -> int:
    return ENTRY_FEE + MULTIPLIER_FEE if multiplied else ENTRY_FEE


def new_ticket(picks: list[int], multiplied: bool) -> dict:
    return {"numbers": picks, "multiplied": multiplied, "cost": entry_cost(multiplied)}


def matches(ticket: dict, winning: list[int]) -> int:
    return len(set(ticket["numbers"]) & set(winning))


def jackpot_share(jackpot: int, winners: int) -> int:
    return jackpot // winners if winners else 0


def next_carried(jackpot: int, winners: int) -> int:
    return STARTING_JACKPOT if winners else jackpot


def _small_prize(ticket: dict, draw: dict) -> dict[str, int]:
    scale = draw["multiplier"] if ticket["multiplied"] else 1
    matched = matches(ticket, draw["numbers"])
    if matched == BALLS_MATCH:
        return {f"balls.{ball}": PRIZE_BALL_AMOUNT * scale for ball in PRIZE_BALLS}
    if matched == ITEMS_MATCH:
        return {f"items.{item}": scale for item in PRIZE_ITEMS}
    return {}


def prize_counters(tickets: list[dict], draw: dict) -> dict[str, int]:
    counters: dict[str, int] = {}
    for ticket in tickets:
        prize = _small_prize(ticket, draw)
        if matches(ticket, draw["numbers"]) == JACKPOT_MATCH:
            prize = {"money": draw["share"], "balls.master": 1}
        for field, amount in prize.items():
            if amount:
                counters[field] = counters.get(field, 0) + amount
    return counters


def roll_key_items(tickets: list[dict], draw: dict, owned_stones: list[str]) -> list[str]:
    jackpots = sum(matches(ticket, draw["numbers"]) == JACKPOT_MATCH for ticket in tickets)
    missing = sorted(KEY_ITEMS - set(owned_stones))
    return random.sample(missing, min(jackpots, len(missing)))
