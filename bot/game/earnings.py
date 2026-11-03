DAILY_LIMIT = 6666


def _earned_on(current: dict | None, day: str) -> int:
    return current["amount"] if current and current["day"] == day else 0


def payable(current: dict | None, amount: int, day: str) -> int:
    return min(amount, max(0, DAILY_LIMIT - _earned_on(current, day)))


def recorded(current: dict | None, paid: int, day: str) -> dict:
    return {"day": day, "amount": _earned_on(current, day) + paid}
