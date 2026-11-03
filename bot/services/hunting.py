from dataclasses import dataclass, field, replace
from datetime import datetime, timezone

from bot.game import battle, catching, creatures, eggs, encounters, ev_training, events, experience, expert_trainers, form_changes, mom_gift, safari
from bot.game.display import DisplayChoice, choice_of
from bot.game.teams import TEAM_SIZE
from bot.services import battle_forms
from bot.services.settling import RewardGain, queued_rewards, settle_pending
from bot.storage.pokemon import as_document, new_id
from bot.storage.stores import Stores

NEEDS_PARTNER = "needs_partner"
EMPTY_TEAM = "empty_team"
IN_BATTLE = "in_battle"
IN_TRADE = "in_trade"
READY = "ready"
SAFARI_READY = "safari_ready"
SAFARI_REMOVED = "safari_removed"
EV_TRAINING_READY = "ev_training_ready"
EV_TRAINING_FINISHED = "ev_training_finished"
EXPERT_READY = "expert_ready"
FOUND = "found"
MOM_GIFT = "mom_gift"
NO_BALL = "no_ball"
THROWN = "thrown"
SWITCHED = "switched"
CANNOT_SWITCH = "cannot_switch"
FORM_CHANGED = "form_changed"
CANNOT_CHANGE_FORM = "cannot_change_form"


@dataclass
class HuntResult:
    status: str
    encounter: dict | None = None
    caught_before: bool = False
    found_tm: str | None = None
    found_stone: str | None = None
    region: str = ""
    hunts: int = 0
    balls: int = 0
    found_egg: bool = False


@dataclass
class BattleState:
    encounter: dict
    balls: dict
    active_team: int
    team_ids: list[str]
    caught_dex: list[int]
    mega_stones: list[str]
    event_reward_day: str | None
    key_stone: bool = False

    @property
    def player(self) -> dict:
        return self.encounter["player"]

    @property
    def has_throwable_ball(self) -> bool:
        return any(self.balls.get(ball, 0) > 0 for ball in catching.THROWABLE_BALLS)

    @property
    def fainted_ids(self) -> list[str]:
        fainted = [member_id for member_id, hp in self.encounter.get("team_hp", {}).items() if hp <= 0]
        if self.encounter["player_hp"] <= 0:
            fainted.append(self.encounter.get("player_id"))
        return fainted

    @property
    def can_go_back(self) -> bool:
        return self.encounter["player_hp"] > 0

    @property
    def form_options(self) -> list[form_changes.FormOption]:
        if self.encounter.get("forms") or not self.can_go_back:
            return []
        items = form_changes.usable_items(self.key_stone, self.mega_stones)
        return form_changes.options_for(self.player["dex_id"], items)


@dataclass
class TurnOutcome:
    state: BattleState
    result: battle.TurnResult
    reward: int = 0
    lost: bool = False
    gains: list[RewardGain] = field(default_factory=list)
    next_state: BattleState | None = None
    money_limited: bool = False

    @property
    def wild_fainted(self) -> bool:
        return self.result.wild_hp <= 0

    @property
    def player_fainted(self) -> bool:
        return self.result.player_hp <= 0


@dataclass
class ThrowOutcome:
    status: str
    state: BattleState | None = None
    stars: int = 0
    caught: bool = False
    counter: battle.TurnResult | None = None
    lost: bool = False
    gains: list[RewardGain] = field(default_factory=list)
    event_reward: int = 0
    held_stone: str | None = None
    fled: bool = False
    drop: catching.FleeDrop | None = None
    money_limited: bool = False

    @property
    def player_fainted(self) -> bool:
        return self.counter is not None and self.counter.player_hp <= 0


@dataclass
class SwitchOutcome:
    status: str
    turn: TurnOutcome | None = None
    called_back: dict | None = None
    forced: bool = False


@dataclass
class FormOutcome:
    status: str
    state: BattleState | None = None
    before: dict | None = None
    option: form_changes.FormOption | None = None


@dataclass
class ExpertStart:
    status: str
    state: BattleState | None = None


@dataclass
class TeamView:
    members: list[dict]
    display: DisplayChoice
    fainted_ids: list[str]


def _state_of(trainer: dict) -> BattleState:
    active_team = trainer["active_team"]
    return BattleState(
        encounter=trainer["encounter"],
        balls=trainer["balls"],
        active_team=active_team,
        team_ids=trainer["teams"][str(active_team)],
        caught_dex=trainer["caught_dex"],
        mega_stones=trainer.get("mega_stones", []),
        event_reward_day=trainer.get("event_reward_day"),
        key_stone=trainer.get("key_stone", False),
    )


def _has_replacement(state: BattleState, active_id: str | None, team_hp: dict) -> bool:
    return any(
        member_id != active_id and team_hp.get(member_id, 1) > 0
        for member_id in state.team_ids
    )


def _end_of_battle_rewards(encounter: dict, participants: list[str], won: bool) -> list[dict]:
    return queued_rewards(encounter["wild"], participants, encounter.get("player_id") if won else None)


async def _busy_result(stores: Stores, trainer_id: int) -> HuntResult:
    in_trade = await stores.trainers.in_trade(trainer_id)
    return HuntResult(IN_TRADE if in_trade else IN_BATTLE)


def today_key() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def event_payout(trainer_id: int, wild: dict, caught: bool, rewarded_day: str | None) -> tuple[str | None, int]:
    today = datetime.now(timezone.utc).date()
    if not caught or wild["dex_id"] != events.daily_event(trainer_id, today) or rewarded_day == today.isoformat():
        return None, 0
    return today.isoformat(), events.event_reward(wild["dex_id"])


async def _find_egg(stores: Stores, trainer_id: int) -> HuntResult:
    egg = eggs.new_egg(new_id(), datetime.now(timezone.utc))
    granted = await stores.trainers.grant_found_egg(trainer_id, egg, encounters.BATTLE_IDLE_SECONDS)
    return HuntResult(FOUND, found_egg=True) if granted else await _busy_result(stores, trainer_id)


async def _find_tm(stores: Stores, trainer_id: int, tm: str) -> HuntResult:
    granted = await stores.trainers.grant_found_tm(trainer_id, tm, encounters.BATTLE_IDLE_SECONDS)
    return HuntResult(FOUND, found_tm=tm) if granted else await _busy_result(stores, trainer_id)


async def _find_stone(stores: Stores, trainer_id: int, stone: str) -> HuntResult:
    granted = await stores.trainers.grant_found_stone(trainer_id, stone, encounters.BATTLE_IDLE_SECONDS)
    return HuntResult(FOUND, found_stone=stone) if granted else await _busy_result(stores, trainer_id)


async def _start_expert_hunt(stores: Stores, trainer_id: int) -> HuntResult:
    encounter = expert_trainers.new_encounter(new_id())
    started = await stores.trainers.start_expert_encounter(trainer_id, encounter, encounters.BATTLE_IDLE_SECONDS)
    return HuntResult(EXPERT_READY, encounter) if started else await _busy_result(stores, trainer_id)


async def _start_safari_hunt(stores: Stores, trainer: dict) -> HuntResult:
    trainer_id = trainer["_id"]
    today = today_key()
    session = trainer["safari"]
    if not safari.can_hunt(session, trainer["balls"].get(safari.BALL, 0), today):
        left = await stores.trainers.leave_safari(trainer_id, encounters.BATTLE_IDLE_SECONDS)
        if left is None:
            return await _busy_result(stores, trainer_id)
        return HuntResult(SAFARI_REMOVED, region=left["region"].title())

    if eggs.roll_found():
        return await _find_egg(stores, trainer_id)
    wild = safari.roll_wild(session["region"])
    encounter = safari.new_encounter(new_id(), wild)
    started = await stores.trainers.start_safari_encounter(
        trainer_id,
        encounter,
        today,
        safari.HUNT_LIMIT,
        encounters.BATTLE_IDLE_SECONDS,
    )
    if started is None:
        return await _busy_result(stores, trainer_id)
    return HuntResult(
        SAFARI_READY,
        encounter,
        wild["dex_id"] in trainer["caught_dex"],
        region=session["region"].title(),
        hunts=started["safari"]["hunts"],
        balls=started["balls"][safari.BALL],
    )


async def _start_ev_training_hunt(stores: Stores, trainer: dict, lead: dict) -> HuntResult:
    trainer_id = trainer["_id"]
    session = trainer["ev_training"]
    if not ev_training.can_hunt(session):
        left = await stores.trainers.leave_ev_training(trainer_id, encounters.BATTLE_IDLE_SECONDS)
        return HuntResult(EV_TRAINING_FINISHED) if left else await _busy_result(stores, trainer_id)

    wild = ev_training.roll_wild(session["region"], session["stat"])
    encounter = ev_training.new_encounter(new_id(), wild, lead)
    started = await stores.trainers.start_ev_training_encounter(
        trainer_id,
        encounter,
        ev_training.HUNT_LIMIT,
        encounters.BATTLE_IDLE_SECONDS,
    )
    if started is None:
        return await _busy_result(stores, trainer_id)
    return HuntResult(
        EV_TRAINING_READY,
        encounter,
        wild["dex_id"] in trainer["caught_dex"],
    )


async def start_hunt(stores: Stores, trainer_id: int) -> HuntResult:
    trainer = await stores.trainers.get(trainer_id)
    if not trainer or trainer.get("first_partner_id") is None:
        return HuntResult(NEEDS_PARTNER)

    await settle_pending(stores, trainer_id, trainer)
    if mom_gift.is_due(trainer) and await stores.trainers.claim_mom_gift(trainer_id, mom_gift.increases()):
        return HuntResult(MOM_GIFT)
    if trainer.get("safari"):
        return await _start_safari_hunt(stores, trainer)
    members = trainer["teams"][str(trainer["active_team"])]
    lead = await stores.pokemon.get(trainer_id, members[0]) if members else None
    if lead is None:
        return HuntResult(EMPTY_TEAM)
    if trainer.get("ev_training"):
        return await _start_ev_training_hunt(stores, trainer, lead)
    if eggs.roll_found():
        return await _find_egg(stores, trainer_id)
    found_tm = encounters.roll_found_tm()
    if found_tm:
        return await _find_tm(stores, trainer_id, found_tm)
    found_stone = encounters.roll_found_stone(trainer.get("mega_stones", []))
    if found_stone:
        return await _find_stone(stores, trainer_id, found_stone)
    if expert_trainers.roll_found():
        return await _start_expert_hunt(stores, trainer_id)
    wild = encounters.roll_wild(trainer["region"])
    encounter = encounters.new_encounter(new_id(), wild, lead)
    started = await stores.trainers.start_encounter(trainer_id, encounter, encounters.BATTLE_IDLE_SECONDS)
    if not started:
        return await _busy_result(stores, trainer_id)
    return HuntResult(READY, encounter, wild["dex_id"] in trainer["caught_dex"])


async def begin_battle(stores: Stores, trainer_id: int, encounter_id: str) -> BattleState | None:
    trainer = await stores.trainers.begin_battle(trainer_id, encounter_id)
    return _state_of(trainer) if trainer else None


async def begin_expert_battle(stores: Stores, trainer_id: int, encounter_id: str) -> ExpertStart | None:
    trainer = await stores.trainers.get(trainer_id)
    encounter = trainer.get("encounter", {}) if trainer else {}
    if encounter.get("id") != encounter_id or encounter.get("state") != "found":
        return None
    await settle_pending(stores, trainer_id, trainer)
    team_number = trainer["active_team"]
    team_ids = trainer["teams"][str(team_number)]
    found = await stores.pokemon.by_ids(trainer_id, team_ids)
    members = [found[member_id] for member_id in team_ids if member_id in found]
    if not members:
        return ExpertStart(EMPTY_TEAM)
    rivals = expert_trainers.rival_team(members)
    started = await stores.trainers.begin_expert_battle(
        trainer_id,
        encounter_id,
        team_number,
        team_ids,
        expert_trainers.battle_fields(members, rivals),
        [rival["dex_id"] for rival in rivals],
    )
    return ExpertStart(READY, _state_of(started)) if started else None


async def _battling_trainer(stores: Stores, trainer_id: int, encounter_id: str) -> dict | None:
    trainer = await stores.trainers.get(trainer_id)
    if not trainer or trainer.get("encounter", {}).get("id") != encounter_id:
        return None
    if trainer["encounter"]["state"] != "battling":
        return None
    return trainer


async def current_state(stores: Stores, trainer_id: int, encounter_id: str) -> BattleState | None:
    trainer = await _battling_trainer(stores, trainer_id, encounter_id)
    return _state_of(trainer) if trainer else None


def _participants(encounter: dict) -> list[str]:
    known = encounter.get("participants") or [encounter.get("player_id")]
    return [pokemon_id for pokemon_id in known if pokemon_id]


async def remember_message(stores: Stores, trainer_id: int, encounter_id: str, chat_id: int, message_id: int) -> None:
    await stores.trainers.set_encounter_message(trainer_id, encounter_id, chat_id, message_id)


async def keep_alive(stores: Stores, trainer_id: int, encounter_id: str) -> None:
    await stores.trainers.touch_encounter(trainer_id, encounter_id)


async def next_fled_encounter(stores: Stores) -> dict | None:
    return await stores.trainers.claim_idle_encounter(encounters.BATTLE_IDLE_SECONDS)


async def fled_encounter(stores: Stores, trainer_id: int, encounter_id: str) -> dict | None:
    trainer = await stores.trainers.get(trainer_id)
    fled = trainer.get("last_fled") if trainer else None
    return fled if fled and fled["id"] == encounter_id else None


async def run_away(stores: Stores, trainer_id: int, encounter_id: str) -> bool:
    return await stores.trainers.end_battle(trainer_id, encounter_id)


async def team_view(stores: Stores, trainer_id: int, encounter_id: str) -> TeamView | None:
    trainer = await _battling_trainer(stores, trainer_id, encounter_id)
    if trainer is None:
        return None
    team_ids = _state_of(trainer).team_ids
    found = await stores.pokemon.by_ids(trainer_id, team_ids)
    members = [found[member_id] for member_id in team_ids if member_id in found]
    members = await battle_forms.overlay(stores, trainer_id, members, trainer)
    return TeamView(members, choice_of(trainer), _state_of(trainer).fainted_ids)


async def change_form(stores: Stores, trainer_id: int, encounter_id: str, form_id: int) -> FormOutcome | None:
    state = await current_state(stores, trainer_id, encounter_id)
    if state is None:
        return None
    option = form_changes.option_with(state.form_options, form_id)
    if option is None:
        return FormOutcome(CANNOT_CHANGE_FORM)
    encounter = state.encounter
    player_id = encounter["player_id"]
    if not await stores.trainers.change_battle_form(trainer_id, encounter_id, player_id, form_id):
        return FormOutcome(CANNOT_CHANGE_FORM)
    before = dict(state.player)
    state.player["form_id"] = form_id
    encounter["forms"] = {player_id: form_id}
    return FormOutcome(FORM_CHANGED, state, before, option)


async def switch_pokemon(
    stores: Stores,
    trainer_id: int,
    encounter_id: str,
    slot: int,
) -> SwitchOutcome | None:
    state = await current_state(stores, trainer_id, encounter_id)
    if state is None:
        return None

    encounter = state.encounter
    outgoing_id = encounter.get("player_id")
    incoming_id = state.team_ids[slot] if 0 <= slot < len(state.team_ids) else None
    member = None
    if incoming_id is not None and incoming_id != outgoing_id:
        member = await stores.pokemon.get(trainer_id, incoming_id)
    if member is None:
        return SwitchOutcome(CANNOT_SWITCH)

    team_hp = {**encounter.get("team_hp", {}), outgoing_id: encounter["player_hp"]}
    incoming = encounters.battle_copy(member)
    if incoming_id in encounter.get("forms", {}):
        incoming["form_id"] = encounter["forms"][incoming_id]
    incoming_hp = team_hp.get(incoming_id, creatures.stats_of(member)["hp"])
    if incoming_hp <= 0:
        return SwitchOutcome(CANNOT_SWITCH)

    forced = encounter["player_hp"] <= 0
    if forced:
        result = battle.TurnResult(player_hp=incoming_hp, wild_hp=encounter["wild_hp"])
    else:
        result = battle.resolve_turn(incoming, encounter["wild"], incoming_hp, encounter["wild_hp"], None)
    lost = result.player_hp <= 0 and not _has_replacement(state, incoming_id, team_hp)
    participants = list(dict.fromkeys([*_participants(encounter), incoming_id]))
    rewards = _end_of_battle_rewards(encounter, participants, won=False) if lost else []
    applied = await stores.trainers.switch_pokemon(
        trainer_id,
        encounter_id,
        encounter["turn"],
        outgoing_id,
        encounter["player_hp"],
        incoming_id,
        incoming,
        result.player_hp,
        lost,
        rewards,
    )
    if not applied:
        return None

    called_back = state.player
    encounter["player"], encounter["player_id"] = incoming, incoming_id
    encounter["player_hp"] = result.player_hp
    encounter["team_hp"] = team_hp
    gains = await settle_pending(stores, trainer_id) if rewards else []
    turn = TurnOutcome(state, result, lost=lost, gains=gains)
    return SwitchOutcome(SWITCHED, turn, called_back, forced)


def _win_reward(encounter: dict) -> int:
    if encounter.get("expert"):
        return expert_trainers.WIN_REWARD
    return 0 if encounter.get("ev_training") else experience.win_reward(encounter["wild"])


async def _send_out_next(
    stores: Stores,
    trainer_id: int,
    state: BattleState,
    result: battle.TurnResult,
) -> TurnOutcome | None:
    encounter = state.encounter
    rival, *remaining = encounter["expert_team"]
    rival_hp = creatures.stats_of(rival)["hp"]
    player_id = encounter["player_id"]
    applied = await stores.trainers.send_out_expert_pokemon(
        trainer_id,
        encounter["id"],
        encounter["turn"],
        result.player_hp,
        player_id,
        rival,
        rival_hp,
        remaining,
        _end_of_battle_rewards(encounter, _participants(encounter), won=True),
    )
    if not applied:
        return None
    encounter["player_hp"], encounter["wild_hp"] = result.player_hp, result.wild_hp
    next_encounter = {
        **encounter,
        "wild": rival,
        "wild_hp": rival_hp,
        "expert_team": remaining,
        "participants": [player_id],
        "turn": encounter["turn"] + 1,
    }
    return TurnOutcome(state, result, next_state=replace(state, encounter=next_encounter))


async def use_move(
    stores: Stores,
    trainer_id: int,
    encounter_id: str,
    move_index: int,
) -> TurnOutcome | None:
    state = await current_state(stores, trainer_id, encounter_id)
    if state is None or not 0 <= move_index < len(state.player["moves"]) or not state.can_go_back:
        return None

    encounter = state.encounter
    result = battle.resolve_turn(
        state.player,
        encounter["wild"],
        encounter["player_hp"],
        encounter["wild_hp"],
        state.player["moves"][move_index],
    )
    won = result.wild_hp <= 0
    if won and encounter.get("expert_team"):
        return await _send_out_next(stores, trainer_id, state, result)
    team_hp = encounter.get("team_hp", {})
    lost = result.player_hp <= 0 and not _has_replacement(state, encounter.get("player_id"), team_hp)
    reward = _win_reward(encounter) if won else 0
    rewards = _end_of_battle_rewards(encounter, _participants(encounter), won) if won or lost else []
    paid = await stores.trainers.apply_turn(
        trainer_id,
        encounter_id,
        encounter["turn"],
        result.player_hp,
        result.wild_hp,
        won or lost,
        reward,
        rewards,
    )
    if paid is None:
        return None
    encounter["player_hp"], encounter["wild_hp"] = result.player_hp, result.wild_hp
    gains = await settle_pending(stores, trainer_id) if rewards else []
    return TurnOutcome(state, result, paid, lost, gains, money_limited=reward > 0 and paid == 0)


async def throw_ball(
    stores: Stores,
    trainer_id: int,
    encounter_id: str,
    ball: str,
) -> ThrowOutcome | None:
    state = await current_state(stores, trainer_id, encounter_id)
    if state is None or ball not in catching.THROWABLE_BALLS or not state.can_go_back:
        return None
    if state.encounter.get("ev_training") or state.encounter.get("expert"):
        return None
    if state.balls.get(ball, 0) < 1:
        return ThrowOutcome(NO_BALL, state)

    encounter = state.encounter
    wild = encounter["wild"]
    stars, caught = catching.roll_catch(
        creatures.stats_of(wild)["hp"],
        encounter["wild_hp"],
        catching.catch_rate_of(wild["dex_id"]),
        catching.ball_bonus(ball, wild, state.player["level"], encounter["turn"], state.caught_dex),
    )
    counter = None
    fled = not caught and catching.rolls_flee(wild["dex_id"])
    drop = catching.roll_flee_drop() if fled else None
    if not caught and not fled:
        counter = battle.resolve_turn(
            state.player,
            wild,
            encounter["player_hp"],
            encounter["wild_hp"],
            None,
        )
    player_hp = counter.player_hp if counter else encounter["player_hp"]
    team_hp = encounter.get("team_hp", {})
    lost = player_hp <= 0 and not _has_replacement(state, encounter.get("player_id"), team_hp)
    battle_over = caught or lost or fled
    rewards = _end_of_battle_rewards(encounter, _participants(encounter), won=False) if lost or fled else []
    event_day, event_reward = event_payout(trainer_id, wild, caught, state.event_reward_day)
    held_stone = catching.roll_held_stone(wild["dex_id"], state.mega_stones) if caught else None
    paid = await stores.trainers.throw_ball(
        trainer_id,
        encounter_id,
        encounter["turn"],
        ball,
        as_document(trainer_id, encounter_id, creatures.with_sort_fields(wild)) if caught else None,
        player_hp,
        battle_over,
        team_number=state.active_team if len(state.team_ids) < TEAM_SIZE else None,
        team_size=TEAM_SIZE,
        rewards=rewards,
        event_day=event_day,
        event_reward=event_reward,
        held_stone=held_stone,
        drop_field=drop.field if drop else None,
        drop_amount=drop.amount if drop else 0,
    )
    if paid is None:
        return None
    money_drop = drop is not None and drop.field == "money"
    money_limited = (event_reward > 0 or money_drop) and paid == 0
    if money_drop:
        drop = replace(drop, amount=paid) if paid else None
    gains = await settle_pending(stores, trainer_id) if rewards else []
    encounter["player_hp"] = player_hp
    state.balls[ball] -= 1
    return ThrowOutcome(
        THROWN,
        state,
        stars,
        caught,
        counter,
        lost,
        gains,
        paid if event_reward else 0,
        held_stone,
        fled,
        drop,
        money_limited,
    )
