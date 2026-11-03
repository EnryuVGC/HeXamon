from math import isqrt

RANK_UNIT = 10000
MAX_RANK = 10
NATIONAL_DEX_SIZE = 1025


def exp_for_rank(rank: int) -> int:
    return rank**2 * RANK_UNIT


def rank_of(exp_points: int) -> int:
    return min(MAX_RANK, isqrt(exp_points // RANK_UNIT))


def to_next_rank(exp_points: int) -> int:
    rank = rank_of(exp_points)
    return exp_for_rank(rank + 1) - exp_points if rank < MAX_RANK else 0


def win_ratio(wins: int, losses: int) -> float:
    return wins / max(losses, 1)


def catch_rate(caught: int, balls_used: int) -> float:
    return 100 * caught / balls_used if balls_used else 0.0


def species_count(dex_ids: set[int]) -> int:
    return sum(1 for dex_id in dex_ids if 1 <= dex_id <= NATIONAL_DEX_SIZE)
