from bisect import bisect_right
from functools import lru_cache

from bot.game import pokedex

STAT_NAMES = ("hp", "attack", "defense", "special_attack", "special_defense", "speed")
MAX_LEVEL = 100
MAX_STAT_EVS = 252
MAX_TOTAL_EVS = 510
MIN_WIN_REWARD = 2
MAX_WIN_REWARD = 8
MAX_REWARD_LEVEL = 100
MAX_REWARD_BASE_EXP = 300
DEFAULT_BASE_EXP = 50
FLAT_EXP_DIVISOR = 7
LEVEL_SCALE_PIVOT = 2000
EXP_SHARE_RATE = 0.5
LOSS_RATE = 1 / 3


def _erratic(n: int) -> float:
    if n < 50:
        return n**3 * (100 - n) / 50
    if n < 68:
        return n**3 * (150 - n) / 100
    if n < 98:
        return n**3 * ((1911 - 10 * n) // 3) / 500
    return n**3 * (160 - n) / 100


def _fluctuating(n: int) -> float:
    if n < 15:
        return n**3 * ((n + 1) // 3 + 24) / 50
    if n < 36:
        return n**3 * (n + 14) / 50
    return n**3 * (n // 2 + 32) / 50


GROWTH_CURVES = {
    "fast": lambda n: 4 * n**3 / 5,
    "medium": lambda n: n**3,
    "medium-slow": lambda n: 6 * n**3 / 5 - 15 * n**2 + 100 * n - 140,
    "slow": lambda n: 5 * n**3 / 4,
    "slow-then-very-fast": _erratic,
    "fast-then-very-slow": _fluctuating,
}


def _species_value(dex_id: int, field: str):
    data = pokedex.entry(dex_id)
    return data.get(field) or pokedex.entry(data.get("species_id") or dex_id).get(field)


@lru_cache(maxsize=None)
def _level_table(growth_rate: str) -> tuple[int, ...]:
    curve = GROWTH_CURVES[growth_rate]
    return tuple(0 if level == 1 else int(curve(level)) for level in range(1, MAX_LEVEL + 1))


def exp_for_level(dex_id: int, level: int) -> int:
    return _level_table(_species_value(dex_id, "growth_rate"))[level - 1]


def level_for_exp(dex_id: int, exp: int) -> int:
    return bisect_right(_level_table(_species_value(dex_id, "growth_rate")), exp)


def level_progress(dex_id: int, level: int, exp: int) -> tuple[int, float]:
    if level >= MAX_LEVEL:
        return 0, 1.0
    floor = exp_for_level(dex_id, level)
    ceiling = exp_for_level(dex_id, level + 1)
    return max(0, ceiling - exp), min(1.0, (exp - floor) / (ceiling - floor))


def exp_from_defeat(dex_id: int, level: int) -> int:
    base_exp = _species_value(dex_id, "base_experience") or DEFAULT_BASE_EXP
    flat = base_exp * level / FLAT_EXP_DIVISOR
    return max(1, int(flat * max(1.0, level * level / LEVEL_SCALE_PIVOT)))


def ev_yield(dex_id: int) -> list[int]:
    yields = _species_value(dex_id, "ev_yield") or {}
    return [yields.get(stat, 0) for stat in STAT_NAMES]


def capped_ev_gain(current: list[int], gain: list[int]) -> list[int]:
    room = MAX_TOTAL_EVS - sum(current)
    capped = []
    for stat_evs, amount in zip(current, gain):
        allowed = min(amount, MAX_STAT_EVS - stat_evs, room)
        capped.append(max(0, allowed))
        room -= capped[-1]
    return capped


def win_reward(wild: dict) -> int:
    base_exp = _species_value(wild["dex_id"], "base_experience") or DEFAULT_BASE_EXP
    level_share = wild["level"] / MAX_REWARD_LEVEL
    species_share = min(base_exp, MAX_REWARD_BASE_EXP) / MAX_REWARD_BASE_EXP
    spread = MAX_WIN_REWARD - MIN_WIN_REWARD
    return MIN_WIN_REWARD + round(spread * (level_share + species_share) / 2)


def battle_rewards(defeated: dict, participant_ids: list[str], winner_id: str | None) -> list[dict]:
    full_exp = exp_from_defeat(defeated["dex_id"], defeated["level"])
    rewards = []
    for pokemon_id in participant_ids:
        if pokemon_id == winner_id:
            rewards.append({"pokemon_id": pokemon_id, "exp": full_exp, "evs": ev_yield(defeated["dex_id"])})
            continue
        rate = LOSS_RATE if winner_id is None else EXP_SHARE_RATE
        rewards.append({"pokemon_id": pokemon_id, "exp": max(1, int(full_exp * rate)), "evs": [0] * len(STAT_NAMES)})
    return rewards
