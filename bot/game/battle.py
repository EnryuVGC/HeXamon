import random
from dataclasses import dataclass, field

from bot.game import creatures, pokedex

PLAYER = "player"
WILD = "wild"
STAB = 1.5
CRITICAL_MULTIPLIER = 1.5
CRITICAL_ODDS = (24, 8, 2)
DODGE_ODDS = CRITICAL_ODDS[0]


@dataclass
class MoveEvent:
    side: str
    move: str
    missed: bool
    damage: int
    effectiveness: float
    critical: bool = False
    dodged: bool = False


@dataclass
class TurnResult:
    player_hp: int
    wild_hp: int
    events: list[MoveEvent] = field(default_factory=list)


def _hits(move: dict) -> int:
    lowest, highest = move.get("min_hits"), move.get("max_hits")
    if lowest and highest:
        return random.randint(lowest, highest)
    return 1


def _rolls_critical(move: dict) -> bool:
    stage = move["crit_rate"] or 0
    return stage >= len(CRITICAL_ODDS) or random.randint(1, CRITICAL_ODDS[stage]) == 1


def damage_of(attacker: dict, defender: dict, move_name: str) -> tuple[int, float, bool]:
    move = pokedex.move_data(move_name)
    effectiveness = pokedex.type_multiplier(move["type"], creatures.form_id(defender))
    if effectiveness == 0:
        return 0, 0.0, False

    if move["damage_class"] == "special":
        attack_stat, defense_stat = "special_attack", "special_defense"
    else:
        attack_stat, defense_stat = "attack", "defense"
    attack = creatures.stats_of(attacker)[attack_stat]
    defense = creatures.stats_of(defender)[defense_stat]
    base = (2 * attacker["level"] / 5 + 2) * move["power"] * (attack / defense) / 50 + 2
    stab = STAB if move["type"] in pokedex.entry(creatures.form_id(attacker))["types"] else 1
    critical = _rolls_critical(move)
    critical_bonus = CRITICAL_MULTIPLIER if critical else 1

    total = 0
    for _ in range(_hits(move)):
        total += max(1, int(base * stab * critical_bonus * effectiveness * random.randint(85, 100) / 100))
    return total, effectiveness, critical


def _lands(move: dict) -> bool:
    accuracy = move["accuracy"]
    return accuracy is None or random.randint(1, 100) <= accuracy


def _turn_order(player: dict, wild: dict, player_move: str, wild_move: str) -> list[str]:
    def rank(pokemon: dict, move_name: str) -> tuple:
        speed = creatures.stats_of(pokemon)["speed"]
        return pokedex.move_data(move_name)["priority"], speed, random.random()

    if rank(player, player_move) >= rank(wild, wild_move):
        return [PLAYER, WILD]
    return [WILD, PLAYER]


def attack(side: str, attacker: dict, defender: dict, defender_hp: int, move_name: str) -> MoveEvent:
    if not _lands(pokedex.move_data(move_name)):
        return MoveEvent(side, move_name, True, 0, 1.0)
    if random.randint(1, DODGE_ODDS) == 1:
        return MoveEvent(side, move_name, False, 0, 1.0, dodged=True)
    damage, effectiveness, critical = damage_of(attacker, defender, move_name)
    return MoveEvent(side, move_name, False, min(damage, defender_hp), effectiveness, critical)


def resolve_turn(
    player: dict,
    wild: dict,
    player_hp: int,
    wild_hp: int,
    player_move: str | None,
) -> TurnResult:
    wild_move = random.choice(wild["moves"])
    result = TurnResult(player_hp=player_hp, wild_hp=wild_hp)
    order = [WILD] if player_move is None else _turn_order(player, wild, player_move, wild_move)

    for side in order:
        if result.player_hp <= 0 or result.wild_hp <= 0:
            break
        attacker, defender = (player, wild) if side == PLAYER else (wild, player)
        move_name = player_move if side == PLAYER else wild_move
        defender_hp = result.wild_hp if side == PLAYER else result.player_hp
        event = attack(side, attacker, defender, defender_hp, move_name)
        if side == PLAYER:
            result.wild_hp -= event.damage
        else:
            result.player_hp -= event.damage
        result.events.append(event)
    return result
