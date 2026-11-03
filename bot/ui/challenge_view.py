from html import escape

from bot.game import challenges as rules
from bot.game import creatures
from bot.ui import battle_view
from bot.ui.texts import text

SETTING_LINE_ORDER = (
    rules.MAX_POKEMON,
    rules.MIN_LEGENDARIES,
    rules.MAX_LEGENDARIES,
    rules.SWITCH,
    rules.FORM_CHANGES,
    rules.SANDBOX,
    rules.RANDOM,
    rules.MAX_LEVEL,
    rules.MIN_LEVEL,
)


def _mention(side: dict) -> str:
    return text("challenge.mention", trainer_id=side["id"], name=escape(side["name"]))


def _setting_value(value: int | bool) -> str:
    if isinstance(value, bool):
        return text("challenge.enabled") if value else text("challenge.disabled")
    return str(value)


def _changed_settings(challenge: dict) -> str:
    lines = [
        text(f"challenge.setting_lines.{name}", value=_setting_value(challenge["settings"][name]))
        for name in SETTING_LINE_ORDER
        if challenge["settings"][name] != rules.DEFAULT_SETTINGS[name]
    ]
    return "\n".join(lines) + "\n\n" if lines else ""


def _ready_line(challenge: dict, side: str) -> str:
    key = "challenge.ready" if challenge[side]["id"] in challenge["ready"] else "challenge.not_ready"
    return text(key, trainer=_mention(challenge[side]))


def prompt_text(challenge: dict) -> str:
    return text(
        "challenge.prompt",
        challenger=_mention(challenge[rules.CHALLENGER]),
        target=_mention(challenge[rules.TARGET]),
        settings=_changed_settings(challenge),
        challenger_ready=_ready_line(challenge, rules.CHALLENGER),
        target_ready=_ready_line(challenge, rules.TARGET),
    )


def settings_text(challenge: dict) -> str:
    return f"{prompt_text(challenge)}\n\n{text('challenge.settings_hint')}"


def picker_text(challenge: dict, name: str) -> str:
    return f"{prompt_text(challenge)}\n\n{text(f'challenge.pickers.{name}')}"


def _pokemon_name(entry: dict) -> str:
    return escape(creatures.shown_name(entry["pokemon"]))


def _vitals(entry: dict) -> dict:
    max_hp = creatures.stats_of(entry["pokemon"])["hp"]
    return {
        "name": _pokemon_name(entry),
        "types": battle_view.types_text(entry["pokemon"]),
        "level": entry["pokemon"]["level"],
        "hp": entry["hp"],
        "max_hp": max_hp,
        "bar": battle_view.hp_bar(entry["hp"], max_hp),
    }


def screen_text(challenge: dict, lead: str = "") -> str:
    side = challenge["current"]
    mine = rules.active(challenge[side])
    theirs = rules.active(challenge[rules.other(side)])
    choosing_next = challenge["phase"] == rules.REPLACE
    screen = text(
        "challenge.screen",
        opponent=text("challenge.side", **_vitals(theirs)),
        trainer=_mention(challenge[side]),
        player=text("challenge.side", **_vitals(mine)),
        moves=text("hunt.choose_next") if choosing_next else "\n".join(battle_view.move_lines(mine["pokemon"])),
    )
    return f"{lead}\n\n{screen}" if lead else screen


def speed_line(challenge: dict, speed_tie: bool) -> str:
    name = _pokemon_name(rules.active(challenge[challenge["current"]]))
    return text("challenge.speed_tie" if speed_tie else "challenge.speed_advantage", name=name)


def opening_lead(challenge: dict, speed_tie: bool) -> str:
    return "\n".join([text("battle.begins"), speed_line(challenge, speed_tie)])


def switch_lead(outcome) -> str:
    entered = text("challenge.entered", name=_pokemon_name(outcome.entered))
    if outcome.forced:
        return "\n".join([entered, speed_line(outcome.challenge, outcome.speed_tie)])
    return entered


def move_lead(outcome) -> str:
    lines = battle_view.event_lines(
        outcome.event,
        _pokemon_name(outcome.attacker),
        _pokemon_name(outcome.defender),
        show_damage=not outcome.fainted,
        dealt_key="challenge.dealt",
    )
    if outcome.fainted:
        lines.append(text("hunt.player_fainted", name=_pokemon_name(outcome.defender)))
    lines.extend(battle_view.level_lines(outcome.gains))
    return "\n".join(lines)


def _defeat_text(challenge: dict) -> str:
    loser = challenge["loser"]
    winner = _mention(challenge[rules.other(loser)])
    defeated = text("challenge.defeated", winner=winner, loser=_mention(challenge[loser]))
    paid = challenge.get("paid_prize", rules.prize(challenge))
    prize_line = text("challenge.prize", amount=paid) if paid else text("hunt.battle_limit")
    return "\n".join([defeated, prize_line])


def result_text(challenge: dict, lead: str = "", gains: list | None = None) -> str:
    outcome = challenge["outcome"]
    if outcome == rules.EXPIRED:
        return text("challenge.expired")
    if outcome == rules.DRAWN:
        parts = [
            text(
                "challenge.drawn",
                challenger=_mention(challenge[rules.CHALLENGER]),
                target=_mention(challenge[rules.TARGET]),
            )
        ]
    else:
        parts = [lead] if lead else []
        if outcome == rules.TIMED_OUT:
            parts.append(
                text("challenge.timed_out", loser=_mention(challenge[challenge["loser"]]), amount=rules.prize(challenge))
            )
        else:
            parts.append(_defeat_text(challenge))
    levels = battle_view.level_lines(gains or [])
    if levels:
        parts.append("\n".join(levels))
    return "\n\n".join(parts)
