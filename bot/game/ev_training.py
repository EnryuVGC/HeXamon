import random

from bot.game import creatures, encounters, experience, pokedex

HUNT_LIMIT = 50
ENTRY_FEE = 50


def new_session(region: str, stat: str) -> dict:
    return {"region": region, "stat": stat, "hunts": 0}


def can_hunt(session: dict) -> bool:
    return session["hunts"] < HUNT_LIMIT


def spawn_pool(region: str, stat: str) -> tuple[int, ...]:
    index = experience.STAT_NAMES.index(stat)
    return tuple(dex_id for dex_id in encounters.regular_pool(region) if experience.ev_yield(dex_id)[index])


def roll_wild(region: str, stat: str) -> dict:
    dex_id = random.choice(spawn_pool(region, stat))
    level_range = pokedex.entry(dex_id)["wild_range"]
    return creatures.new_pokemon(dex_id, random.randint(level_range["min"], level_range["max"]))


def new_encounter(encounter_id: str, wild: dict, lead: dict) -> dict:
    return {**encounters.new_encounter(encounter_id, wild, lead), "ev_training": True}
