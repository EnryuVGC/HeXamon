from html import escape
from math import ceil

from bot.data import catalog
from bot.game import battle, creatures, experience, mom_gift, pokedex, pokedex_entries
from bot.game.catching import ITEM_DROPS, MASTER_BALL_DROP, MONEY_GIFT, TM_DROP, FleeDrop
from bot.game.form_changes import FormOption
from bot.game.inventory import stone_name
from bot.game.mega_evolutions import KEY_ITEMS
from bot.ui import pokemon_list
from bot.ui.texts import text

ARTWORK_URL = "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/other/official-artwork/{dex_id}.png"
SHINY_ARTWORK_URL = "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/other/official-artwork/shiny/{dex_id}.png"
HP_BAR_LENGTH = 10
ALERT_LENGTH_LIMIT = 200


def artwork(dex_id: int, shiny: bool = False) -> str:
    posted = catalog.form_artwork(pokedex.entry(dex_id)["name"], shiny)
    if posted:
        return posted
    return (SHINY_ARTWORK_URL if shiny else ARTWORK_URL).format(dex_id=pokedex_entries.artwork_id(dex_id))


def hp_bar(hp: int, max_hp: int) -> str:
    filled = ceil(hp * HP_BAR_LENGTH / max_hp)
    return "█" * filled + "░" * (HP_BAR_LENGTH - filled)


def wild_name(encounter: dict) -> str:
    wild = encounter["wild"]
    name = pokedex.species_name(wild["dex_id"])
    return text("hunt.shiny_name", name=name) if wild.get("shiny") else name


def fled_text(encounter: dict) -> str:
    if encounter.get("expert"):
        return text("hunt.expert_left")
    return text("hunt.fled", name=wild_name(encounter))


def all_fainted_text(encounter: dict) -> str:
    return text("hunt.expert_won" if encounter.get("expert") else "hunt.all_fainted")


def expert_fainted_text(encounter: dict, follow_up: str) -> str:
    return "\n".join([text("hunt.expert_fainted", name=wild_name(encounter)), follow_up])


def held_stone_text(name: str, stone: str) -> str:
    key = "hunt.held_item" if stone in KEY_ITEMS else "hunt.held_stone"
    return text(key, name=name, stone=stone_name(stone))


def found_stone_text(stone: str) -> str:
    return text("hunt.found_item" if stone in KEY_ITEMS else "hunt.found_stone", stone=stone_name(stone))


def flee_drop_text(drop: FleeDrop) -> str:
    if drop.kind == MONEY_GIFT:
        return text("hunt.drop_money", amount=drop.amount)
    if drop.kind == MASTER_BALL_DROP:
        return text("hunt.drop_master")
    if drop.kind == TM_DROP:
        return text("hunt.drop_tm", number=drop.tm)
    if drop.kind in ITEM_DROPS:
        return text(f"hunt.drop_{drop.kind}", count=drop.amount)
    key = "hunt.drop_ball" if drop.amount == 1 else "hunt.drop_balls"
    return text(key, count=drop.amount, ball=drop.ball.title())


def safari_appeared_text(encounter: dict, caught_before: bool, hunts: int, limit: int, balls: int) -> str:
    footer = text("safari.appeared_footer", hunts=hunts, limit=limit, balls=balls)
    return f"{appeared_text(encounter, caught_before)}\n\n{footer}"


def ev_training_appeared_text(encounter: dict, caught_before: bool) -> str:
    gains = text("hunt.ev_separator").join(
        text("ev_training.ev_gain", amount=amount, stat=text(f"hunt.ev_stats.{stat}"))
        for stat, amount in zip(experience.STAT_NAMES, experience.ev_yield(encounter["wild"]["dex_id"]))
        if amount
    )
    return f"{appeared_text(encounter, caught_before)}\n{gains}"


def safari_prompt_text(balls: int) -> str:
    return text("safari.prompt", balls=balls)


def appeared_text(encounter: dict, caught_before: bool) -> str:
    wild = encounter["wild"]
    marker = text("hunt.caught_marker") if caught_before else ""
    return text("hunt.appeared", name=wild_name(encounter), level=wild["level"], marker=marker)


def types_text(pokemon: dict) -> str:
    return text("battle.type_separator").join(pokedex.type_names(creatures.form_id(pokemon)))


def move_lines(pokemon: dict) -> list[str]:
    lines = []
    for name in pokemon["moves"]:
        move = pokedex.move_data(name)
        accuracy = move["accuracy"] if move["accuracy"] is not None else text("battle.never_misses_accuracy")
        lines.append(
            text(
                "battle.move",
                name=pokedex.display_name(name),
                type=pokedex.display_name(move["type"]),
                power=move["power"],
                accuracy=accuracy,
            )
        )
    return lines


def battle_text(
    state,
    trainer_id: int,
    trainer_name: str,
    opening: bool = False,
    action: str = "",
    choosing_next: bool = False,
) -> str:
    encounter = state.encounter
    wild = encounter["wild"]
    player = state.player
    wild_max_hp = creatures.stats_of(wild)["hp"]
    player_max_hp = creatures.stats_of(player)["hp"]

    screen = text(
        "battle.screen",
        opponent=text("battle.expert_label" if encounter.get("expert") else "battle.wild_label"),
        wild_name=wild_name(encounter),
        wild_types=types_text(wild),
        wild_level=wild["level"],
        wild_hp=encounter["wild_hp"],
        wild_max_hp=wild_max_hp,
        wild_bar=hp_bar(encounter["wild_hp"], wild_max_hp),
        trainer_id=trainer_id,
        trainer_name=escape(trainer_name),
        player_name=escape(creatures.shown_name(player)),
        player_types=types_text(player),
        player_level=player["level"],
        player_hp=encounter["player_hp"],
        player_max_hp=player_max_hp,
        player_bar=hp_bar(encounter["player_hp"], player_max_hp),
        moves=text("hunt.choose_next") if choosing_next else "\n".join(move_lines(player)),
    )
    parts = [text("battle.begins")] if opening else []
    if action:
        parts.append(action)
    parts.append(screen)
    return "\n\n".join(parts)


def event_lines(
    event: battle.MoveEvent,
    attacker: str,
    defender: str,
    show_damage: bool = True,
    dealt_key: str = "battle.dealt",
) -> list[str]:
    move = pokedex.display_name(event.move)
    if event.missed:
        return [text("battle.missed", attacker=attacker, move=move)]
    if event.dodged:
        return [text("battle.used", attacker=attacker, move=move), text("battle.dodged", name=defender)]
    if event.effectiveness == 0:
        return [text("battle.used", attacker=attacker, move=move), text("battle.immune")]
    lines = [text("battle.used", attacker=attacker, move=move)]
    if event.critical:
        lines.append(text("battle.critical"))
    if event.effectiveness > 1:
        lines.append(text("battle.super_effective"))
    elif event.effectiveness < 1:
        lines.append(text("battle.not_very_effective"))
    if show_damage:
        lines.append(text(dealt_key, damage=event.damage))
    return lines


def _side_name(state, side: str) -> str:
    if side == battle.PLAYER:
        return escape(creatures.shown_name(state.player))
    return wild_name(state.encounter)


def _other_side(side: str) -> str:
    return battle.WILD if side == battle.PLAYER else battle.PLAYER


def action_text(state, event: battle.MoveEvent) -> str:
    attacker = _side_name(state, event.side)
    defender = _side_name(state, _other_side(event.side))
    return "\n".join(event_lines(event, attacker, defender))


def finishing_text(state, event: battle.MoveEvent) -> str:
    attacker = _side_name(state, event.side)
    defender = _side_name(state, _other_side(event.side))
    return "\n".join(event_lines(event, attacker, defender, show_damage=False))


def fainting_text(state, event: battle.MoveEvent) -> str:
    defender = _side_name(state, _other_side(event.side))
    return "\n".join([finishing_text(state, event), text("hunt.player_fainted", name=defender)])


def attacking_text(state, event: battle.MoveEvent) -> str:
    attacking = text("battle.attacking", name=_side_name(state, _other_side(event.side)))
    return f"{action_text(state, event)}\n\n{attacking}"


def switched_text(state, called_back: dict) -> str:
    switched = text(
        "battle.switched",
        called_back=escape(creatures.shown_name(called_back)),
        sent_out=escape(creatures.shown_name(state.player)),
    )
    attacking = text("battle.attacking", name=wild_name(state.encounter))
    return f"{switched}\n\n{attacking}"


def _mega_form_name(form_id: int) -> str:
    extra = [word for word in pokedex.form_label(form_id).split() if word != text("battle.mega_word")]
    return text("battle.mega_form", species=pokedex.base_species_name(form_id), extra=" ".join(extra)).strip()


def form_change_text(before: dict, option: FormOption) -> str:
    name = escape(creatures.shown_name(before))
    if option.item in KEY_ITEMS:
        form = text(f"battle.form_names.{option.item}")
        return text("battle.form_item_used", name=name, item=stone_name(option.item), form=form)
    return text("battle.mega_evolved", name=name, form=_mega_form_name(option.form_id))


def _team_line(number: int, pokemon: dict, display_key: str) -> str:
    name = creatures.shown_name(pokemon)
    detail = pokemon_list.detail(pokemon, display_key)
    badges = pokemon_list.badges(pokemon)
    if detail:
        return text("battle.team_line_detail", number=number, name=name, detail=detail) + badges
    return text("battle.team_line", number=number, name=name) + badges


def team_alert(view) -> str:
    lines = []
    for number, pokemon in enumerate(view.members, start=1):
        line = _team_line(number, pokemon, view.display.key)
        if str(pokemon["_id"]) in view.fainted_ids:
            line = text("battle.team_line_fainted", line=line)
        lines.append(line)
    return "\n".join(lines)[:ALERT_LENGTH_LIMIT]


def _stat_gains(evs: list[int]) -> str:
    return text("hunt.ev_separator").join(
        text("hunt.ev_amount", amount=amount, stat=text(f"hunt.ev_stats.{stat}"))
        for stat, amount in zip(experience.STAT_NAMES, evs)
        if amount
    )


def _mom_gift_lines(group: str, counts: dict) -> list[str]:
    return [
        text("hunt.mom_gift_line", amount=amount, label=text(f"inventory.{group}.{key}.many"))
        for key, amount in counts.items()
    ]


def mom_gift_text() -> str:
    lines = [
        text("hunt.mom_gift_money", amount=mom_gift.MONEY),
        *_mom_gift_lines("balls", mom_gift.BALLS),
        *_mom_gift_lines("items", mom_gift.ITEMS),
    ]
    return text("hunt.mom_gift", rewards="\n".join(lines))


def ev_yield_alert(dex_id: int) -> str:
    return text("hunt.ev_yield", yields=_stat_gains(experience.ev_yield(dex_id)) or text("hunt.ev_none"))


def level_lines(gains: list) -> list[str]:
    return [
        text("hunt.level_up", name=escape(creatures.shown_name(gain.pokemon)), level=gain.new_level)
        for gain in gains
        if gain.new_level > gain.old_level
    ]


def ready_to_evolve_text(pokemon: dict) -> str:
    return text("evolve.ready", level=pokemon["level"], name=escape(creatures.shown_name(pokemon)))


def learned_lines(gains: list) -> str:
    lines = []
    for gain in gains:
        name = escape(creatures.shown_name(gain.pokemon))
        for move in gain.learned:
            lines.append(text("hunt.move_learned", name=name, move=pokedex.display_name(move)))
    return "\n".join(lines)


def catch_frames(ball: str, stars: int, caught: bool) -> list[str]:
    label = text(f"inventory.balls.{ball}.one")
    key = "hunt.ball_used_vowel" if label[0] in "AEIOU" else "hunt.ball_used"
    frames = [text(key, ball=label, progress=text("hunt.catch_dot") * count) for count in range(1, stars + 1)]
    if caught:
        frames.append(text(key, ball=label, progress=text("hunt.star") * stars))
    return frames or [text(key, ball=label, progress="")]
