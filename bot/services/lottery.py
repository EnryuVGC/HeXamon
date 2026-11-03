from dataclasses import dataclass, field
from datetime import datetime, timezone

from bot.game import lottery as rules
from bot.storage.stores import Stores

SAVED = "saved"
NO_MONEY = "no_money"
MAX_REACHED = "max_reached"
DUPLICATE = "duplicate"
DRAWING = "drawing"


@dataclass(frozen=True)
class Overview:
    jackpot: int
    tickets: list[dict]


@dataclass(frozen=True)
class LastDraw:
    draw: dict
    tickets: list[dict]


@dataclass(frozen=True)
class Winnings:
    trainer_id: int
    day: str
    numbers: list[int]
    counters: dict[str, int]
    key_items: list[str] = field(default_factory=list)
    money_limited: bool = False


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _today() -> str:
    return rules.draw_day(_now())


def seconds_until_draw() -> int:
    return rules.seconds_until_draw(_now())


def _tickets_for(trainer: dict | None, day: str) -> list[dict]:
    lottery = (trainer or {}).get("lottery", {})
    return lottery.get("tickets", []) if lottery.get("day") == day else []


async def _jackpot(stores: Stores, day: str) -> int:
    draw = await stores.lottery.get(day) or {}
    fees = draw.get("fees", 0)
    if "carried" in draw:
        return draw["carried"] + fees
    previous = await stores.lottery.latest_before(day)
    if previous is None:
        return rules.STARTING_JACKPOT + fees
    return previous.get("carried", rules.STARTING_JACKPOT) + previous.get("fees", 0) + fees


async def overview(stores: Stores, trainer_id: int) -> Overview:
    today = _today()
    trainer = await stores.trainers.get(trainer_id)
    return Overview(await _jackpot(stores, today), _tickets_for(trainer, today))


def _refusal(trainer: dict | None, today: str, ticket: dict) -> str:
    lottery = (trainer or {}).get("lottery")
    if lottery and lottery["day"] != today:
        return DRAWING
    tickets = _tickets_for(trainer, today)
    if len(tickets) >= rules.MAX_ENTRIES:
        return MAX_REACHED
    if any(held["numbers"] == ticket["numbers"] for held in tickets):
        return DUPLICATE
    return NO_MONEY


async def save_entry(stores: Stores, trainer_id: int, picks: list[int], multiplied: bool) -> str:
    today = _today()
    ticket = rules.new_ticket(picks, multiplied)
    await stores.lottery.ensure_draw(today)
    if not await stores.trainers.buy_lottery_ticket(trainer_id, today, ticket, rules.MAX_ENTRIES):
        return _refusal(await stores.trainers.get(trainer_id), today, ticket)
    await stores.lottery.add_fees(today, ticket["cost"])
    return SAVED


async def last_draw(stores: Stores, trainer_id: int) -> LastDraw | None:
    draw = await stores.lottery.latest_done()
    if draw is None:
        return None
    trainer = await stores.trainers.get(trainer_id) or {}
    day = draw["_id"]
    tickets = _tickets_for(trainer, day)
    if not tickets and trainer.get("last_lottery", {}).get("day") == day:
        tickets = trainer["last_lottery"]["tickets"]
    return LastDraw(draw, tickets)


async def _run_due_draws(stores: Stores, today: str) -> None:
    while (draw := await stores.lottery.oldest_open_before(today)) is not None:
        day = draw["_id"]
        numbers = rules.roll_winning_numbers()
        fees, winners = await stores.trainers.lottery_totals(day, numbers)
        jackpot = draw.get("carried", rules.STARTING_JACKPOT) + fees
        jackpot_winners = winners.get(rules.JACKPOT_MATCH, 0)
        await stores.lottery.set_carried(rules.next_day(day), rules.next_carried(jackpot, jackpot_winners))
        await stores.lottery.finish(
            day,
            {
                "numbers": numbers,
                "multiplier": rules.roll_multiplier(),
                "jackpot": jackpot,
                "share": rules.jackpot_share(jackpot, jackpot_winners),
                "winners": {str(matched): count for matched, count in winners.items()},
            },
        )


async def next_winnings(stores: Stores) -> Winnings | None:
    today = _today()
    await stores.lottery.ensure_draw(today)
    await _run_due_draws(stores, today)
    while (player := await stores.trainers.next_lottery_player(today)) is not None:
        lottery = player["lottery"]
        draw = await stores.lottery.get(lottery["day"])
        counters = rules.prize_counters(lottery["tickets"], draw)
        key_items = rules.roll_key_items(lottery["tickets"], draw, player.get("mega_stones", []))
        paid = await stores.trainers.pay_lottery_player(player["_id"], lottery, counters, key_items)
        if paid is not None and (counters or key_items):
            money_limited = counters.get("money", 0) > 0 and paid == 0
            shown = {prize: amount for prize, amount in counters.items() if prize != "money"}
            if paid:
                shown = {"money": paid, **shown}
            return Winnings(player["_id"], lottery["day"], draw["numbers"], shown, key_items, money_limited)
    return None
