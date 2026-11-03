import random

from bot.game import creatures, encounters, pokedex

ENCOUNTER_ODDS = 200
WIN_REWARD = 125
CLOSEST_SPECIES = 15


def roll_found() -> bool:
    return random.randint(1, ENCOUNTER_ODDS) == 1


def new_encounter(encounter_id: str) -> dict:
    return {"id": encounter_id, "state": "found", "turn": 0, "expert": True}


def _base_total(dex_id: int) -> int:
    return sum(pokedex.entry(dex_id)["stats"].values())


def _rival_of(member: dict, used: set[int]) -> dict:
    target = _base_total(member["dex_id"])
    choices = [dex_id for dex_id in encounters.regular_spawns() if dex_id not in used]
    closest = sorted(choices, key=lambda dex_id: abs(_base_total(dex_id) - target))[:CLOSEST_SPECIES]
    dex_id = random.choice(closest)
    used.add(dex_id)
    rival = creatures.new_pokemon(dex_id, member["level"])
    return {**rival, "ivs": member["ivs"], "evs": creatures.evs_of(member)}


def rival_team(members: list[dict]) -> list[dict]:
    used = set()
    return [_rival_of(member, used) for member in members]


def battle_fields(members: list[dict], rivals: list[dict]) -> dict:
    lead = members[0]
    return {
        "wild": rivals[0],
        "wild_hp": creatures.stats_of(rivals[0])["hp"],
        "expert_team": rivals[1:],
        "player": encounters.battle_copy(lead),
        "player_id": str(lead["_id"]),
        "player_hp": creatures.stats_of(lead)["hp"],
        "team_hp": {},
        "participants": [str(lead["_id"])],
    }
