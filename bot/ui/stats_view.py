from html import escape

from bot.game import creatures, display as display_rules, experience, pokedex
from bot.game.stats_pages import INFO, IVS, MOVES, STATS
from bot.ui import pokemon_list
from bot.ui.texts import text

EXP_BAR_LENGTH = 10
SHOWN_MOVE_EFFECTS = ("burn", "paralysis", "poison", "freeze", "sleep", "confusion", "trap")


def _exp_bar(progress: float) -> str:
    filled = round(progress * EXP_BAR_LENGTH)
    return "█" * filled + "▒" * (EXP_BAR_LENGTH - filled)


def _types(pokemon: dict) -> str:
    return text("battle.type_separator").join(
        text(
            "stats.type",
            name=pokedex.display_name(type_name),
            symbol=text(f"display.type_symbols.{type_name}"),
        )
        for type_name in display_rules.raw_types(pokemon)
    )


def _info_text(pokemon: dict) -> str:
    exp = creatures.current_exp(pokemon)
    to_next, progress = experience.level_progress(pokemon["dex_id"], pokemon["level"], exp)
    label = "stats.types_label" if len(display_rules.raw_types(pokemon)) > 1 else "stats.type_label"
    return text(
        "stats.info",
        level=pokemon["level"],
        nature=pokemon["nature"],
        badges="".join(f" {badge}" for badge in pokemon_list.badge_list(pokemon)),
        types_label=text(label),
        types=_types(pokemon),
        exp=exp,
        to_next=to_next,
        bar=_exp_bar(progress),
    )


def _stat_marker(stat: str, raised: str | None, lowered: str | None) -> str:
    if stat == raised:
        return text("stats.raised_marker")
    if stat == lowered:
        return text("stats.lowered_marker")
    return ""


def _stats_text(pokemon: dict) -> str:
    stats = creatures.stats_of(pokemon)
    raised, lowered = creatures.nature_effects(pokemon)
    return "\n".join(
        text(
            "stats.stat_line",
            label=text(f"hunt.ev_stats.{stat}"),
            value=stats[stat],
            marker=_stat_marker(stat, raised, lowered),
        )
        for stat in experience.STAT_NAMES
    )


def _move_text(name: str) -> str:
    move = pokedex.move_data(name)
    accuracy = move["accuracy"] if move["accuracy"] is not None else text("battle.never_misses_accuracy")
    lines = [
        text(
            "stats.move",
            name=pokedex.display_name(name),
            type=pokedex.display_name(move["type"]),
            symbol=text(f"display.type_symbols.{move['type']}"),
            power=move["power"],
            accuracy=accuracy,
            category=pokedex.display_name(move["damage_class"]),
        )
    ]
    if move.get("ailment") in SHOWN_MOVE_EFFECTS:
        lines.append(text("stats.move_effect", effect=text(f"stats.move_effects.{move['ailment']}")))
    return "\n".join(lines)


def _moves_text(pokemon: dict) -> str:
    return "\n".join(_move_text(name) for name in pokemon["moves"])


def _ivs_text(pokemon: dict) -> str:
    ivs = pokemon["ivs"]
    evs = creatures.evs_of(pokemon)
    rows = "\n".join(
        text("stats.points_row", label=text(f"hunt.ev_stats.{stat}"), iv=iv, ev=ev)
        for stat, iv, ev in zip(experience.STAT_NAMES, ivs, evs)
    )
    return text(
        "stats.points_table",
        header=text("stats.points_header"),
        rule=text("stats.points_rule"),
        rows=rows,
        total=text("stats.points_total", label=text("stats.total_label"), iv=sum(ivs), ev=sum(evs)),
    )


def _inspected_points(values: list[int]) -> str:
    return "\n".join(
        text("stats.inspect_row", label=text(f"hunt.ev_stats.{stat}"), value=value)
        for stat, value in zip(experience.STAT_NAMES, values)
    )


def inspect_text(pokemon: dict) -> str:
    ivs = pokemon["ivs"]
    evs = creatures.evs_of(pokemon)
    return text(
        "stats.inspect",
        name=escape(creatures.shown_name(pokemon)),
        ivs=_inspected_points(ivs),
        iv_total=sum(ivs),
        evs=_inspected_points(evs),
        ev_total=sum(evs),
    )


PAGE_TEXTS = {INFO: _info_text, STATS: _stats_text, MOVES: _moves_text, IVS: _ivs_text}


def page_text(page: str, pokemon: dict) -> str:
    return PAGE_TEXTS[page](pokemon)
