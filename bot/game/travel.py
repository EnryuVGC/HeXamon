from bot.data import catalog
from bot.game.trainer_stats import exp_for_rank, rank_of


def all_regions() -> list[str]:
    return catalog.load("regions")


def unlocked_regions(exp_points: int) -> list[str]:
    return all_regions()[: rank_of(exp_points) + 1]


def minimum_exp(region_index: int) -> int:
    return exp_for_rank(region_index)


def region_key(region: str) -> str:
    return region.casefold()
