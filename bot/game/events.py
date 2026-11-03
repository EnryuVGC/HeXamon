from datetime import date
from random import Random

from bot.game import catching, encounters, pokedex

REWARD_TIERS = ((30, 800), (60, 550), (120, 400), (190, 300))
COMMON_REWARD = 200


def daily_event(trainer_id: int, day: date) -> int:
    return Random(f"{trainer_id}:{day.isoformat()}").choice(encounters.regular_spawns())


def event_reward(dex_id: int) -> int:
    catch_rate = catching.catch_rate_of(dex_id)
    for highest_rate, reward in REWARD_TIERS:
        if catch_rate <= highest_rate:
            return reward
    return COMMON_REWARD


def event_name(dex_id: int) -> str:
    return pokedex.species_name(dex_id)
