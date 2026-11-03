import random

from bot.data import catalog
from bot.game import experience, pokedex
from bot.game.catching import catch_rate_of
from bot.game.experience import STAT_NAMES
from bot.game.ivs import MAX_IV, roll_ivs

NATURE_STATS = {
    "Attack": "attack",
    "Defense": "defense",
    "Sp. Atk": "special_attack",
    "Sp. Def": "special_defense",
    "Speed": "speed",
}
SHINY_ODDS = 10000


def new_pokemon(dex_id: int, level: int) -> dict:
    learnable = pokedex.learnable_moves(dex_id, level)
    return {
        "dex_id": dex_id,
        "level": level,
        "nature": random.choice(list(catalog.load("natures"))),
        "exp": experience.exp_for_level(dex_id, level),
        "ivs": roll_ivs(dex_id),
        "evs": [0] * len(STAT_NAMES),
        "moves": random.sample(learnable, min(pokedex.MAX_MOVES, len(learnable))),
        "nickname": None,
    }


def _has_shiny_artwork(dex_id: int) -> bool:
    name = pokedex.entry(dex_id)["name"]
    return catalog.form_artwork(name, True) is not None or catalog.form_artwork(name, False) is None


def with_shiny_roll(pokemon: dict) -> dict:
    return {**pokemon, "shiny": random.randint(1, SHINY_ODDS) == 1 and _has_shiny_artwork(pokemon["dex_id"])}


def evs_of(pokemon: dict) -> list[int]:
    return pokemon.get("evs") or [0] * len(STAT_NAMES)


def current_exp(pokemon: dict) -> int:
    return max(pokemon.get("exp") or 0, experience.exp_for_level(pokemon["dex_id"], pokemon["level"]))


def nature_effects(pokemon: dict) -> tuple[str | None, str | None]:
    nature = catalog.load("natures")[pokemon["nature"]]
    return NATURE_STATS.get(nature["increases"]), NATURE_STATS.get(nature["decreases"])


def form_id(pokemon: dict) -> int:
    return pokemon.get("form_id") or pokemon["dex_id"]


def stats_of(pokemon: dict) -> dict:
    base = pokedex.entry(form_id(pokemon))["stats"]
    base_hp = pokedex.entry(pokemon["dex_id"])["stats"]["hp"]
    level = pokemon["level"]
    ivs = dict(zip(STAT_NAMES, pokemon["ivs"]))
    evs = dict(zip(STAT_NAMES, evs_of(pokemon)))
    raised, lowered = nature_effects(pokemon)

    stats = {"hp": (2 * base_hp + ivs["hp"] + evs["hp"] // 4) * level // 100 + level + 10}
    for stat in STAT_NAMES[1:]:
        value = (2 * base[stat] + ivs[stat] + evs[stat] // 4) * level // 100 + 5
        if stat == raised:
            value = value * 110 // 100
        elif stat == lowered:
            value = value * 90 // 100
        stats[stat] = value
    return stats


def with_sort_fields(pokemon: dict) -> dict:
    data = pokedex.entry(pokemon["dex_id"])
    stats = stats_of({**pokemon, "form_id": None})
    return {
        **pokemon,
        "name": (pokemon["nickname"] or pokedex.plain_name(pokemon["dex_id"])).casefold(),
        "type": data["types"][0],
        "catch_rate": catch_rate_of(pokemon["dex_id"]),
        "iv_total": sum(pokemon["ivs"]),
        "ev_total": sum(evs_of(pokemon)),
        "stats": [stats[name] for name in STAT_NAMES],
        "stat_total": sum(stats.values()),
    }


def with_form(pokemon: dict, form: int) -> dict:
    changed = {**pokemon, "form_id": form}
    stats = stats_of(changed)
    return {
        **changed,
        "type": pokedex.entry(form)["types"][0],
        "stats": [stats[name] for name in STAT_NAMES],
        "stat_total": sum(stats.values()),
    }


def after_reward(pokemon: dict, exp: int, evs: list[int]) -> dict:
    dex_id = pokemon["dex_id"]
    old_exp = current_exp(pokemon)
    new_exp = min(old_exp + exp, experience.exp_for_level(dex_id, experience.MAX_LEVEL))
    old_evs = evs_of(pokemon)
    evs_gained = experience.capped_ev_gain(old_evs, evs)
    new_level = max(pokemon["level"], experience.level_for_exp(dex_id, new_exp))
    grown = {
        **pokemon,
        "exp": new_exp,
        "level": new_level,
        "evs": [current + gained for current, gained in zip(old_evs, evs_gained)],
        "moves": _moves_after_level_up(pokemon, new_level),
    }
    sorted_fields = with_sort_fields(grown)
    names = ("exp", "level", "evs", "ev_total", "stats", "stat_total", "moves")
    return {name: sorted_fields[name] for name in names}


def at_level(pokemon: dict, level: int) -> dict:
    changed = with_sort_fields({**pokemon, "level": level, "exp": experience.exp_for_level(pokemon["dex_id"], level)})
    names = ("level", "exp", "stats", "stat_total")
    return {name: changed[name] for name in names}


def with_ivs(pokemon: dict, ivs: list[int]) -> dict:
    changed = with_sort_fields({**pokemon, "ivs": ivs})
    names = ("ivs", "iv_total", "stats", "stat_total")
    return {name: changed[name] for name in names}


def with_nature(pokemon: dict, nature: str) -> dict:
    changed = with_sort_fields({**pokemon, "nature": nature})
    names = ("nature", "stats", "stat_total")
    return {name: changed[name] for name in names}


def after_ev_change(pokemon: dict, evs: list[int]) -> dict:
    changed = with_sort_fields({**pokemon, "evs": evs})
    names = ("evs", "ev_total", "stats", "stat_total")
    return {name: changed[name] for name in names}


def after_evolution(pokemon: dict, new_dex_id: int) -> dict:
    level = pokemon["level"]
    exp = current_exp(pokemon)
    if experience.level_for_exp(new_dex_id, exp) != level:
        exp = experience.exp_for_level(new_dex_id, level)
    evolved = with_sort_fields({**pokemon, "dex_id": new_dex_id, "exp": exp})
    names = ("dex_id", "exp", "name", "type", "catch_rate", "stats", "stat_total")
    return {name: evolved[name] for name in names}


def after_trade(dex_id: int) -> dict:
    return {"nickname": None, "name": pokedex.plain_name(dex_id).casefold()}


def _moves_after_level_up(pokemon: dict, new_level: int) -> list[str]:
    moves = list(pokemon["moves"])
    for move in pokedex.moves_gained_between(pokemon["dex_id"], pokemon["level"], new_level):
        if len(moves) < pokedex.MAX_MOVES and move not in moves:
            moves.append(move)
    return moves


def shown_name(pokemon: dict) -> str:
    form = form_id(pokemon)
    if not pokemon["nickname"]:
        return pokedex.species_name(form)
    return pokedex.with_form_label(pokemon["nickname"], form) if form != pokemon["dex_id"] else pokemon["nickname"]
