from datetime import date

from bot.game import lottery as rules
from bot.game.inventory import stone_name
from bot.ui.texts import text

NUMBER_JOINER = "–"
BALL_FIELD = "balls."


def numbers_text(numbers: list[int]) -> str:
    return NUMBER_JOINER.join(map(str, numbers))


def _mark(multiplied: bool) -> str:
    return text("lottery.mark_on" if multiplied else "lottery.mark_off")


def menu_text(jackpot: int) -> str:
    return text("lottery.menu", fee=rules.ENTRY_FEE, plays=rules.MAX_ENTRIES, jackpot=jackpot)


def info_text() -> str:
    return text("lottery.info", amount=rules.PRIZE_BALL_AMOUNT)


def picker_text(picks: list[int], multiplied: bool) -> str:
    return text(
        "lottery.picker",
        count=rules.NUMBER_COUNT,
        highest=rules.HIGHEST_NUMBER,
        selected=numbers_text(picks) or text("lottery.none_selected"),
        mark=_mark(multiplied),
        cost=rules.entry_cost(multiplied),
    )


def saved_text(picks: list[int], multiplied: bool) -> str:
    fees = text("lottery.saved_fee", fee=rules.ENTRY_FEE)
    if multiplied:
        fees = f"{fees}\n\n{text('lottery.saved_multiplier_fee', fee=rules.MULTIPLIER_FEE)}"
    return text("lottery.saved", fees=fees, numbers=numbers_text(picks))


def _ticket_block(ticket: dict) -> str:
    return text(
        "lottery.entry",
        numbers=numbers_text(ticket["numbers"]),
        mark=_mark(ticket["multiplied"]),
    )


def _entry_blocks(tickets: list[dict]) -> str:
    rule = text("lottery.entry_rule")
    return "\n".join([rule, *(f"{_ticket_block(ticket)}\n{rule}" for ticket in tickets)])


def entries_text(jackpot: int, tickets: list[dict]) -> str:
    entries = _entry_blocks(tickets) if tickets else text("lottery.no_entries")
    return text("lottery.entries", jackpot=jackpot, entries=entries)


def countdown_text(seconds: int) -> str:
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return text("lottery.countdown", hours=hours, minutes=minutes, seconds=seconds)


def _date_text(day: str) -> str:
    drawn = date.fromisoformat(day)
    return f"{drawn:%A, %B} {drawn.day}, {drawn.year}"


def last_text(draw: dict, tickets: list[dict]) -> str:
    winners = draw["winners"]
    entries = f"\n{_entry_blocks(tickets)}" if tickets else f" {text('lottery.no_entries')}"
    return text(
        "lottery.last",
        date=_date_text(draw["_id"]),
        jackpot=draw["jackpot"],
        numbers=numbers_text(draw["numbers"]),
        multiplier=draw["multiplier"],
        five=winners.get(str(rules.JACKPOT_MATCH), 0),
        four=winners.get(str(rules.BALLS_MATCH), 0),
        three=winners.get(str(rules.ITEMS_MATCH), 0),
        entries=entries,
    )


def _prize_line(field: str, amount: int) -> str:
    if field == "money":
        return text("lottery.prize_money", amount=amount)
    if field.startswith(BALL_FIELD):
        return text("lottery.prize_ball", amount=amount, ball=field.removeprefix(BALL_FIELD).title())
    return text(f"lottery.prize_{field.removeprefix('items.')}", amount=amount)


def winnings_text(
    day: str,
    numbers: list[int],
    counters: dict[str, int],
    key_items: list[str],
    money_limited: bool = False,
) -> str:
    lines = [_prize_line(field, amount) for field, amount in counters.items()]
    lines.extend(text("lottery.prize_key_item", item=stone_name(item)) for item in key_items)
    if money_limited:
        lines.append(text("hunt.earning_limit"))
    return text(
        "lottery.winnings",
        date=_date_text(day),
        numbers=numbers_text(numbers),
        prizes="\n".join(lines),
    )
