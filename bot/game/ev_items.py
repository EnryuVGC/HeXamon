from bot.game.experience import MAX_STAT_EVS, MAX_TOTAL_EVS

VITAMIN = "vitamin"
BERRY = "berry"
EV_ITEM_POINTS = 10


def after_item(evs: list[int], item: str, stat: int) -> list[int]:
    current = evs[stat]
    if item == BERRY:
        changed = max(0, current - EV_ITEM_POINTS)
    else:
        room = min(MAX_STAT_EVS - current, MAX_TOTAL_EVS - sum(evs))
        changed = current + max(0, min(EV_ITEM_POINTS, room))
    return [changed if index == stat else value for index, value in enumerate(evs)]


def can_use(evs: list[int], item: str, stat: int) -> bool:
    return after_item(evs, item, stat) != evs


def can_use_on_any_stat(evs: list[int], item: str) -> bool:
    return any(can_use(evs, item, stat) for stat in range(len(evs)))
