import random
from dataclasses import dataclass, field

from bot.data import catalog
from bot.game import creatures, encounters, form_changes, ivs

WAITING_SECONDS = 180
TURN_SECONDS = 90
RETRY_SECONDS = 30
FINISHED_KEPT_SECONDS = 30 * 24 * 60 * 60
PRIZE_PER_POKEMON = 15

WAITING = "waiting"
JOINING = "joining"
BATTLING = "battling"
SETTLING = "settling"
DONE = "done"

WON = "won"
TIMED_OUT = "timed_out"
DRAWN = "drawn"
EXPIRED = "expired"

CHALLENGER = "challenger"
TARGET = "target"
SIDES = (CHALLENGER, TARGET)

MOVE = "move"
REPLACE = "replace"

TEAM_SIZE_LIMIT = 6
LEVELS_PER_RANGE = 10

MAX_POKEMON = "max_pokemon"
MIN_LEGENDARIES = "min_legendaries"
MAX_LEGENDARIES = "max_legendaries"
MIN_LEVEL = "min_level"
MAX_LEVEL = "max_level"
SWITCH = "switch"
FORM_CHANGES = "form_changes"
SANDBOX = "sandbox"
RANDOM = "random"
DEFAULT_SETTINGS = {
    MAX_POKEMON: TEAM_SIZE_LIMIT,
    MIN_LEGENDARIES: 0,
    MAX_LEGENDARIES: TEAM_SIZE_LIMIT,
    MIN_LEVEL: 1,
    MAX_LEVEL: 100,
    SWITCH: True,
    FORM_CHANGES: True,
    SANDBOX: False,
    RANDOM: False,
}
TOGGLE_SETTINGS = (SWITCH, FORM_CHANGES, SANDBOX, RANDOM)
LEVEL_SETTINGS = (MIN_LEVEL, MAX_LEVEL)
SETTING_VALUES = {
    MAX_POKEMON: range(1, TEAM_SIZE_LIMIT + 1),
    MIN_LEGENDARIES: range(0, TEAM_SIZE_LIMIT + 1),
    MAX_LEGENDARIES: range(0, TEAM_SIZE_LIMIT + 1),
    MIN_LEVEL: range(1, 101),
    MAX_LEVEL: range(1, 101),
}


@dataclass
class Payout:
    money: int = 0
    wins: int = 0
    losses: int = 0
    rewards: list[dict] = field(default_factory=list)


def settings_from(saved: dict | None) -> dict:
    return {name: (saved or {}).get(name, default) for name, default in DEFAULT_SETTINGS.items()}


def fits_together(settings: dict, name: str, value: int) -> bool:
    chosen = {**settings, name: value}
    return (
        chosen[MIN_LEVEL] <= chosen[MAX_LEVEL]
        and chosen[MIN_LEGENDARIES] <= chosen[MAX_LEGENDARIES]
        and chosen[MIN_LEGENDARIES] <= chosen[MAX_POKEMON]
    )


def level_ranges() -> list[tuple[int, int]]:
    return [(start, start + LEVELS_PER_RANGE - 1) for start in range(1, 101, LEVELS_PER_RANGE)]


def legendary_ids() -> list[int]:
    return [int(dex_id) for dex_id in catalog.load("pokedex") if ivs.is_special(int(dex_id))]


def team_meets_settings(settings: dict, pokemon: list[dict]) -> bool:
    legendaries = sum(1 for member in pokemon if ivs.is_special(member["dex_id"]))
    return (
        len(pokemon) <= settings[MAX_POKEMON]
        and settings[MIN_LEGENDARIES] <= legendaries <= settings[MAX_LEGENDARIES]
        and all(settings[MIN_LEVEL] <= member["level"] <= settings[MAX_LEVEL] for member in pokemon)
    )


def random_team(settings: dict, legendaries: list[dict], others: list[dict]) -> list[dict]:
    most = min(settings[MAX_LEGENDARIES], settings[MAX_POKEMON], len(legendaries))
    if most < settings[MIN_LEGENDARIES]:
        return []
    count = random.randint(settings[MIN_LEGENDARIES], most)
    team = legendaries[:count] + others[: settings[MAX_POKEMON] - count]
    random.shuffle(team)
    return team


def side_of(name: str, trainer_id: int) -> dict:
    return {"id": trainer_id, "name": name}


def other(side: str) -> str:
    return TARGET if side == CHALLENGER else CHALLENGER


def side_named(challenge: dict, trainer_id: int) -> str | None:
    for side in SIDES:
        if challenge[side]["id"] == trainer_id:
            return side
    return None


def team_entry(pokemon: dict) -> dict:
    return {
        "id": str(pokemon["_id"]),
        "pokemon": encounters.battle_copy(pokemon),
        "hp": creatures.stats_of(pokemon)["hp"],
    }


def battle_side(team: list[dict], form_items: list[str]) -> dict:
    return {"team": team, "active": 0, "facing": [team[0]["id"]], "rewards": [], "form_items": form_items}


def form_items_of(settings: dict, trainer: dict) -> list[str]:
    if not settings[FORM_CHANGES]:
        return []
    return form_changes.usable_items(trainer.get("key_stone", False), trainer.get("mega_stones", []))


def active(side: dict) -> dict:
    return side["team"][side["active"]]


def form_options(side: dict) -> list[form_changes.FormOption]:
    if side.get("form_used"):
        return []
    return form_changes.options_for(active(side)["pokemon"]["dex_id"], side.get("form_items", []))


def team_forms(side: dict) -> dict[str, int]:
    return {entry["id"]: entry["pokemon"]["form_id"] for entry in side["team"] if entry["pokemon"].get("form_id")}


def has_replacement(side: dict) -> bool:
    return any(entry["hp"] > 0 for slot, entry in enumerate(side["team"]) if slot != side["active"])


def first_side(challenge: dict) -> tuple[str, bool]:
    speeds = {side: creatures.stats_of(active(challenge[side])["pokemon"])["speed"] for side in SIDES}
    if speeds[CHALLENGER] == speeds[TARGET]:
        return random.choice(SIDES), True
    return max(SIDES, key=speeds.get), False


def facing_after_entry(side: dict, entered_id: str) -> list[str]:
    return list(dict.fromkeys([*side["facing"], entered_id]))


def growth_fields(side_name: str, side: dict, pokemon_id: str, fields: dict) -> tuple[dict, dict]:
    for slot, entry in enumerate(side["team"]):
        if entry["id"] != pokemon_id:
            continue
        grown = {**entry["pokemon"], "level": fields["level"], "evs": fields["evs"], "moves": fields["moves"]}
        hp_gain = creatures.stats_of(grown)["hp"] - creatures.stats_of(entry["pokemon"])["hp"]
        raised = {f"{side_name}.team.{slot}.hp": hp_gain} if entry["hp"] > 0 and hp_gain else {}
        return {f"{side_name}.team.{slot}.pokemon": grown}, raised
    return {}, {}


def prize(challenge: dict) -> int:
    return len(challenge[challenge["loser"]]["team"]) * PRIZE_PER_POKEMON


def payout(challenge: dict, side: str) -> Payout:
    rewards = challenge[side].get("rewards", [])
    if challenge["outcome"] not in (WON, TIMED_OUT):
        return Payout(rewards=rewards)
    if challenge["loser"] == side:
        fine = prize(challenge) if challenge["outcome"] == TIMED_OUT else 0
        return Payout(money=-fine, losses=1, rewards=rewards)
    return Payout(money=prize(challenge), wins=1, rewards=rewards)
