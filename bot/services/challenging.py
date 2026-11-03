from dataclasses import dataclass, field

from bot.game import battle, form_changes
from bot.game import challenges as rules
from bot.game.display import choice_of
from bot.game.encounters import BATTLE_IDLE_SECONDS
from bot.services import battle_forms
from bot.services.hunting import TeamView
from bot.services.settling import RewardGain, apply_reward, queued_rewards, settle_pending
from bot.storage.stores import Stores

CREATED = "created"
OTHER_NOT_STARTED = "other_not_started"
WAITING = "waiting"
ALREADY_STARTING = "already_starting"
STARTED = "started"
ENDED = "ended"

SWITCHED = "switched"
CANNOT_SWITCH = "cannot_switch"
SWITCH_DISABLED = "switch_disabled"

FORM_CHANGED = "form_changed"
CANNOT_CHANGE_FORM = "cannot_change_form"

OFFERED = "offered"
DRAWN = "drawn"


@dataclass
class ChallengeRequest:
    status: str
    challenge_id: str | None = None


@dataclass
class Readiness:
    status: str
    challenge: dict | None = None
    fled: list[dict] = field(default_factory=list)
    speed_tie: bool = False


@dataclass
class Settled:
    challenge: dict
    gains: list[RewardGain] = field(default_factory=list)


@dataclass
class MoveOutcome:
    challenge: dict
    event: battle.MoveEvent
    attacker: dict
    defender: dict
    fainted: bool
    gains: list[RewardGain] = field(default_factory=list)


@dataclass
class SwitchOutcome:
    status: str
    challenge: dict | None = None
    entered: dict | None = None
    forced: bool = False
    speed_tie: bool = False


@dataclass
class FormOutcome:
    status: str
    challenge: dict | None = None
    before: dict | None = None
    option: form_changes.FormOption | None = None


@dataclass
class DrawOutcome:
    status: str
    settled: Settled | None = None


async def _busy_status(stores: Stores, trainer_id: int, prefix: str) -> str | None:
    await settle_pending(stores, trainer_id)
    if await stores.trainers.can_trade(trainer_id, BATTLE_IDLE_SECONDS):
        return None
    in_trade = await stores.trainers.in_trade(trainer_id)
    return f"{prefix}_in_trade" if in_trade else f"{prefix}_in_battle"


async def request(
    stores: Stores,
    challenger_id: int,
    challenger_name: str,
    target_id: int,
    target_name: str,
    chat_id: int,
) -> ChallengeRequest:
    if not await stores.trainers.has_started(target_id):
        return ChallengeRequest(OTHER_NOT_STARTED)
    blocked = await _busy_status(stores, challenger_id, "you") or await _busy_status(stores, target_id, "other")
    if blocked is not None:
        return ChallengeRequest(blocked)
    challenge_id = await stores.challenges.create(
        rules.side_of(challenger_name, challenger_id),
        rules.side_of(target_name, target_id),
        chat_id,
        rules.settings_from((await stores.trainers.get(challenger_id)).get("challenge_settings")),
    )
    return ChallengeRequest(CREATED, challenge_id)


async def remember_message(stores: Stores, challenge_id: str, message_id: int) -> None:
    await stores.challenges.set_message(challenge_id, message_id)


async def get(stores: Stores, challenge_id: str) -> dict | None:
    return await stores.challenges.get(challenge_id)


async def set_setting(stores: Stores, challenge: dict, name: str, value: int | bool) -> dict | None:
    challenger_id = challenge[rules.CHALLENGER]["id"]
    return await stores.challenges.set_setting(str(challenge["_id"]), challenger_id, challenge["settings"], name, value)


async def save_settings(stores: Stores, challenge: dict) -> None:
    await stores.trainers.save_challenge_settings(challenge[rules.CHALLENGER]["id"], challenge["settings"])


async def _random_team(stores: Stores, trainer_id: int, settings: dict) -> list[dict]:
    levels = {"level": {"$gte": settings[rules.MIN_LEVEL], "$lte": settings[rules.MAX_LEVEL]}}
    legendary_ids = rules.legendary_ids()
    size = settings[rules.MAX_POKEMON]
    legendaries = await stores.pokemon.random_sample(trainer_id, {**levels, "dex_id": {"$in": legendary_ids}}, size)
    others = await stores.pokemon.random_sample(trainer_id, {**levels, "dex_id": {"$nin": legendary_ids}}, size)
    return rules.random_team(settings, legendaries, others)


async def _active_team(stores: Stores, trainer_id: int) -> list[dict]:
    trainer = await stores.trainers.get(trainer_id)
    team_ids = trainer["teams"][str(trainer["active_team"])]
    found = await stores.pokemon.by_ids(trainer_id, team_ids)
    return [found[member_id] for member_id in team_ids if member_id in found]


async def _battle_team(stores: Stores, trainer_id: int, settings: dict, prefix: str) -> tuple[list[dict], str | None]:
    if settings[rules.RANDOM]:
        team = await _random_team(stores, trainer_id, settings)
        return team, None if team else f"{prefix}_cannot_field"
    team = await _active_team(stores, trainer_id)
    if not team:
        return team, f"{prefix}_empty_team"
    if not rules.team_meets_settings(settings, team):
        return team, f"{prefix}_team_invalid"
    return team, None


async def _undo_joining(stores: Stores, challenge: dict) -> dict | None:
    challenge_id = str(challenge["_id"])
    for side in rules.SIDES:
        await stores.trainers.finish_challenge(challenge[side]["id"], challenge_id, rules.Payout())
    await stores.challenges.reopen(challenge_id, challenge[rules.CHALLENGER]["id"])
    return await stores.challenges.get(challenge_id)


async def press_ready(stores: Stores, challenge: dict, trainer_id: int) -> Readiness:
    challenge_id = str(challenge["_id"])
    if trainer_id in challenge["ready"]:
        updated = await stores.challenges.unmark_ready(challenge_id, trainer_id)
        return Readiness(WAITING, updated) if updated else Readiness(ENDED)
    updated = await stores.challenges.mark_ready(challenge_id, trainer_id)
    if updated is None:
        return Readiness(ENDED)
    if len(updated["ready"]) < len(rules.SIDES):
        return Readiness(WAITING, updated)

    pressing_side = rules.side_named(challenge, trainer_id)
    other_side = rules.other(pressing_side)
    other_id = challenge[other_side]["id"]
    blocked = await _busy_status(stores, trainer_id, "you") or await _busy_status(stores, other_id, "other")
    if blocked is not None:
        return Readiness(blocked, await stores.challenges.unmark_ready(challenge_id, trainer_id))
    joining = await stores.challenges.begin_joining(challenge_id)
    if joining is None:
        return Readiness(ALREADY_STARTING)

    fled = []
    for side in rules.SIDES:
        joined = await stores.trainers.join_challenge(joining[side]["id"], challenge_id, BATTLE_IDLE_SECONDS)
        if joined is None:
            reopened = await _undo_joining(stores, joining)
            blocked = await _busy_status(stores, trainer_id, "you") or await _busy_status(stores, other_id, "other")
            return Readiness(blocked or "you_in_battle", reopened, fled)
        if "encounter" in joined:
            fled.append(joined["encounter"])

    sides = {}
    for side, prefix in ((pressing_side, "you"), (other_side, "other")):
        team, problem = await _battle_team(stores, joining[side]["id"], joining["settings"], prefix)
        if problem is not None:
            return Readiness(problem, await _undo_joining(stores, joining), fled)
        owner = await stores.trainers.get(joining[side]["id"])
        items = rules.form_items_of(joining["settings"], owner)
        sides[side] = rules.battle_side([rules.team_entry(member) for member in team], items)

    current, speed_tie = rules.first_side(sides)
    started = await stores.challenges.start_battle(challenge_id, sides, current)
    if started is None:
        return Readiness(ENDED, fled=fled)
    return Readiness(STARTED, started, fled, speed_tie)


def _faint_rewards(challenge: dict, side: str, foe: str) -> dict:
    if challenge["settings"][rules.SANDBOX]:
        return {}
    winner, loser = challenge[side], challenge[foe]
    victor, fainted = rules.active(winner), rules.active(loser)
    return {
        side: queued_rewards(fainted["pokemon"], winner["facing"], victor["id"]),
        foe: queued_rewards(victor["pokemon"], loser["facing"], None),
    }


async def _grow_team(stores: Stores, challenge: dict, rewards: dict) -> tuple[dict, list[RewardGain]]:
    gains, fields, raised = [], {}, {}
    for side, queued in rewards.items():
        for reward in queued:
            gain = await apply_reward(stores, challenge[side]["id"], reward)
            if gain is None:
                continue
            gains.append(gain)
            changed, hp_raised = rules.growth_fields(side, challenge[side], reward["pokemon_id"], gain.fields)
            fields.update(changed)
            raised.update(hp_raised)
    if not fields:
        return challenge, gains
    grown = await stores.challenges.grow_team(str(challenge["_id"]), challenge["turn"], fields, raised)
    return grown or challenge, gains


async def use_move(stores: Stores, challenge: dict, move_index: int) -> MoveOutcome | None:
    side = challenge["current"]
    foe = rules.other(side)
    attacker, defender = rules.active(challenge[side]), rules.active(challenge[foe])
    moves = attacker["pokemon"]["moves"]
    if challenge["phase"] != rules.MOVE or not 0 <= move_index < len(moves):
        return None

    event = battle.attack(side, attacker["pokemon"], defender["pokemon"], defender["hp"], moves[move_index])
    defender["hp"] -= event.damage
    fields = {f"{foe}.team.{challenge[foe]['active']}.hp": defender["hp"], "current": foe}
    fainted = defender["hp"] <= 0
    rewards = _faint_rewards(challenge, side, foe) if fainted else {}
    if fainted and rules.has_replacement(challenge[foe]):
        fields["phase"] = rules.REPLACE
    elif fainted:
        fields.update({"state": rules.SETTLING, "outcome": rules.WON, "loser": foe})

    updated = await stores.challenges.advance(str(challenge["_id"]), challenge["turn"], fields, rewards)
    if updated is None:
        return None
    if updated["state"] == rules.SETTLING:
        settled = await settle(stores, updated)
        return MoveOutcome(settled.challenge, event, attacker, defender, fainted, settled.gains)
    grown, gains = await _grow_team(stores, updated, rewards)
    return MoveOutcome(grown, event, attacker, defender, fainted, gains)


async def switch(stores: Stores, challenge: dict, slot: int) -> SwitchOutcome | None:
    side = challenge["current"]
    foe = rules.other(side)
    mine, theirs = challenge[side], challenge[foe]
    forced = challenge["phase"] == rules.REPLACE
    if not forced and not challenge["settings"][rules.SWITCH]:
        return SwitchOutcome(SWITCH_DISABLED)
    entry = mine["team"][slot] if 0 <= slot < len(mine["team"]) else None
    if entry is None or entry["hp"] <= 0 or slot == mine["active"]:
        return SwitchOutcome(CANNOT_SWITCH)

    mine["active"] = slot
    current, speed_tie = rules.first_side(challenge) if forced else (foe, False)
    fields = {
        f"{side}.active": slot,
        f"{side}.facing": rules.facing_after_entry(mine, entry["id"]),
        f"{foe}.facing": [rules.active(theirs)["id"]],
        "current": current,
        "phase": rules.MOVE,
    }
    updated = await stores.challenges.advance(str(challenge["_id"]), challenge["turn"], fields)
    if updated is None:
        return None
    return SwitchOutcome(SWITCHED, updated, entry, forced, speed_tie)


async def change_form(stores: Stores, challenge: dict, form_id: int) -> FormOutcome | None:
    side = challenge["current"]
    mine = challenge[side]
    option = form_changes.option_with(rules.form_options(mine), form_id)
    if challenge["phase"] != rules.MOVE or option is None:
        return FormOutcome(CANNOT_CHANGE_FORM)
    before = dict(rules.active(mine)["pokemon"])
    updated = await stores.challenges.change_form(
        str(challenge["_id"]), challenge["turn"], side, mine["active"], form_id
    )
    if updated is None:
        return None
    return FormOutcome(FORM_CHANGED, updated, before, option)


async def offer_draw(stores: Stores, challenge_id: str, trainer_id: int) -> DrawOutcome | None:
    if await stores.challenges.offer_draw(challenge_id, trainer_id) is None:
        return None
    closing = await stores.challenges.close_as_draw(challenge_id)
    if closing is None:
        return DrawOutcome(OFFERED)
    return DrawOutcome(DRAWN, await settle(stores, closing))


async def team_view(stores: Stores, challenge: dict, trainer_id: int) -> TeamView | None:
    trainer = await stores.trainers.get(trainer_id)
    if trainer is None:
        return None
    team = challenge[rules.side_named(challenge, trainer_id)]["team"]
    found = await stores.pokemon.by_ids(trainer_id, [entry["id"] for entry in team])
    members = [found[entry["id"]] for entry in team if entry["id"] in found]
    members = battle_forms.apply_forms(members, rules.team_forms(challenge[rules.side_named(challenge, trainer_id)]))
    fainted_ids = [entry["id"] for entry in team if entry["hp"] <= 0]
    return TeamView(members, choice_of(trainer), fainted_ids)


async def settle(stores: Stores, challenge: dict) -> Settled:
    challenge_id = str(challenge["_id"])
    if challenge["state"] != rules.SETTLING:
        return Settled(challenge)
    paid_prize = None
    for side in rules.SIDES:
        payout = rules.payout(challenge, side)
        paid = await stores.trainers.finish_challenge(challenge[side]["id"], challenge_id, payout)
        if payout.money > 0 and paid is not None:
            paid_prize = paid
    gains = []
    for side in rules.SIDES:
        gains.extend(await settle_pending(stores, challenge[side]["id"]))
    finished = await stores.challenges.finish(challenge_id, paid_prize)
    return Settled(finished or await stores.challenges.get(challenge_id), gains)


async def next_settled(stores: Stores) -> Settled | None:
    challenge = await stores.challenges.claim_unfinished() or await stores.challenges.claim_expired()
    return await settle(stores, challenge) if challenge else None
