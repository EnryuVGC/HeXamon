import random

from bot.data import catalog
from bot.game import creatures, pokedex

BALL = "safari"
STARTING_BALLS = 30
BALL_BONUS = 2.3
HUNT_LIMIT = 200
ENTRY_FEE = 150
RARE_GROUPS = (("arceus", 0.2), ("silvally-", 0.05))


def new_session(region: str, day: str) -> dict:
    return {"region": region, "day": day, "hunts": 0}


def is_active(session: dict | None, day: str) -> bool:
    return session is not None and session["day"] == day


def can_hunt(session: dict, balls: int, day: str) -> bool:
    return is_active(session, day) and session["hunts"] < HUNT_LIMIT and balls > 0


def _roll_dex_id(region: str) -> int:
    pool = catalog.load("safari_encounters")[region]
    roll = random.random()
    grouped = set()
    for prefix, chance in RARE_GROUPS:
        group = [dex_id for dex_id in pool if pokedex.entry(dex_id)["name"].startswith(prefix)]
        grouped.update(group)
        if group and roll < chance:
            return random.choice(group)
        if group:
            roll -= chance
    return random.choice([dex_id for dex_id in pool if dex_id not in grouped])


def roll_wild(region: str) -> dict:
    dex_id = _roll_dex_id(region)
    level_range = pokedex.entry(dex_id)["wild_range"]
    level = random.randint(level_range["min"], level_range["max"])
    return creatures.with_shiny_roll(creatures.new_pokemon(dex_id, level))


def new_encounter(encounter_id: str, wild: dict) -> dict:
    return {
        "id": encounter_id,
        "state": "found",
        "safari": True,
        "turn": 0,
        "wild": wild,
        "wild_hp": creatures.stats_of(wild)["hp"],
    }
