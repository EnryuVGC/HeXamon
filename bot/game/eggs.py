import random
from datetime import datetime, timedelta
from functools import lru_cache

from bot.data import catalog
from bot.game import creatures, encounters
from bot.game.ivs import roll_egg_ivs

EGG_ODDS = 50000
HATCH_SECONDS = 86400
HATCH_LEVEL = 1


def roll_found() -> bool:
    return random.randint(1, EGG_ODDS) == 1


def new_egg(egg_id: str, now: datetime) -> dict:
    return {"id": egg_id, "hatch_at": now + timedelta(seconds=HATCH_SECONDS)}


@lru_cache(maxsize=None)
def hatch_pool() -> tuple[int, ...]:
    evolved = {
        target
        for data in catalog.load("evolutions").values()
        for target in data.get("evolution") or []
    }
    return tuple(dex_id for dex_id in encounters.regular_spawns() if dex_id not in evolved)


def hatch() -> dict:
    pokemon = creatures.new_pokemon(random.choice(hatch_pool()), HATCH_LEVEL)
    return {**creatures.with_shiny_roll(pokemon), "ivs": roll_egg_ivs(), "egg": True}
