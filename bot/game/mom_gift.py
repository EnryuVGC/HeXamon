MONEY = 1000
BALLS = {"great": 10, "ultra": 5}
ITEMS = {"rare_candy": 5, "vitamin": 5, "berry": 5}


def is_due(trainer: dict) -> bool:
    return not trainer.get("mom_gift") and not trainer.get("seen_dex")


def increases() -> dict:
    return {
        "money": MONEY,
        **{f"balls.{ball}": amount for ball, amount in BALLS.items()},
        **{f"items.{item}": amount for item, amount in ITEMS.items()},
    }
