MAX_GIFT = 1000000000


def parse_amount(args: str | None) -> int | None:
    words = (args or "").split()
    if len(words) != 1 or not (words[0].isascii() and words[0].isdecimal()) or len(words[0]) > len(str(MAX_GIFT)):
        return None
    amount = int(words[0])
    return amount if 1 <= amount <= MAX_GIFT else None
