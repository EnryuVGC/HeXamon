from dataclasses import dataclass

from bot.game import catching, creatures, encounters, safari as rules
from bot.game.teams import TEAM_SIZE
from bot.services.hunting import IN_BATTLE, IN_TRADE, event_payout, today_key
from bot.services.settling import settle_pending
from bot.storage.pokemon import as_document
from bot.storage.stores import Stores

ENTERED = "entered"
ALREADY_INSIDE = "already_inside"
ALREADY_PLAYED = "already_played"
NO_MONEY = "no_money"
OPEN = "open"
IN_EV_TRAINING = "in_ev_training"


@dataclass
class SafariStatus:
    status: str
    region: str = ""
    hunts: int = 0
    balls: int = 0


@dataclass
class SafariThrow:
    wild: dict
    encounter_id: str
    stars: int
    caught: bool
    fled: bool
    balls: int
    region: str
    event_reward: int = 0
    held_stone: str | None = None
    money_limited: bool = False

    @property
    def out_of_balls(self) -> bool:
        return self.balls < 1


def _inside(trainer: dict) -> SafariStatus:
    session = trainer["safari"]
    return SafariStatus(
        ALREADY_INSIDE,
        session["region"].title(),
        session["hunts"],
        trainer["balls"].get(rules.BALL, 0),
    )


def _status_of(trainer: dict, today: str) -> SafariStatus:
    if "ev_training" in trainer:
        return SafariStatus(IN_EV_TRAINING)
    if rules.is_active(trainer.get("safari"), today):
        return _inside(trainer)
    if trainer.get("safari_day") == today:
        return SafariStatus(ALREADY_PLAYED)
    return SafariStatus(OPEN, trainer["region"].title())


async def status_of(stores: Stores, trainer_id: int) -> SafariStatus:
    return _status_of(await stores.trainers.get(trainer_id), today_key())


async def enter(stores: Stores, trainer_id: int) -> SafariStatus:
    today = today_key()
    trainer = await stores.trainers.get(trainer_id)
    status = _status_of(trainer, today)
    if status.status != OPEN:
        return status
    session = rules.new_session(trainer["region"], today)
    entered = await stores.trainers.enter_safari(
        trainer_id,
        session,
        rules.STARTING_BALLS,
        rules.ENTRY_FEE,
        encounters.BATTLE_IDLE_SECONDS,
    )
    if entered:
        return SafariStatus(ENTERED, status.region, 0, rules.STARTING_BALLS)
    if await stores.trainers.in_trade(trainer_id):
        return SafariStatus(IN_TRADE)
    if trainer.get("money", 0) < rules.ENTRY_FEE:
        return SafariStatus(NO_MONEY)
    return _status_of(await stores.trainers.get(trainer_id), today) if trainer.get("safari_day") == today else SafariStatus(IN_BATTLE)


async def leave(stores: Stores, trainer_id: int) -> str | None:
    session = await stores.trainers.leave_safari(trainer_id)
    return session["region"].title() if session else None


async def begin_catch(stores: Stores, trainer_id: int, encounter_id: str) -> tuple[dict, int] | None:
    trainer = await stores.trainers.begin_battle(trainer_id, encounter_id)
    if trainer is None:
        return None
    return trainer["encounter"]["wild"], trainer["balls"].get(rules.BALL, 0)


async def throw_ball(stores: Stores, trainer_id: int, encounter_id: str) -> SafariThrow | None:
    trainer = await stores.trainers.get(trainer_id)
    encounter = trainer.get("encounter", {}) if trainer else {}
    balls = trainer["balls"].get(rules.BALL, 0) if trainer else 0
    if encounter.get("id") != encounter_id or encounter.get("state") != "battling" or balls < 1:
        return None

    wild = encounter["wild"]
    hp = creatures.stats_of(wild)["hp"]
    stars, caught = catching.roll_catch(hp, hp, catching.catch_rate_of(wild["dex_id"]), rules.BALL_BONUS)
    fled = not caught and catching.rolls_flee(wild["dex_id"])
    last_ball = balls == 1
    event_day, event_reward = event_payout(trainer_id, wild, caught, trainer.get("event_reward_day"))
    held_stone = catching.roll_held_stone(wild["dex_id"], trainer.get("mega_stones", [])) if caught else None
    active_team = trainer["active_team"]
    paid = await stores.trainers.throw_ball(
        trainer_id,
        encounter_id,
        encounter["turn"],
        rules.BALL,
        as_document(trainer_id, encounter_id, creatures.with_sort_fields(wild)) if caught else None,
        0,
        caught or fled or last_ball,
        team_number=active_team if len(trainer["teams"][str(active_team)]) < TEAM_SIZE else None,
        team_size=TEAM_SIZE,
        event_day=event_day,
        event_reward=event_reward,
        held_stone=held_stone,
        leave_safari=last_ball,
    )
    if paid is None:
        return None
    if caught:
        await settle_pending(stores, trainer_id)
    return SafariThrow(
        wild,
        encounter_id,
        stars,
        caught,
        fled,
        balls - 1,
        trainer["safari"]["region"].title(),
        paid,
        held_stone,
        event_reward > 0 and paid == 0,
    )
