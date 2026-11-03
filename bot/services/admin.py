from dataclasses import dataclass
from datetime import datetime, timezone

from bot.game import admin as rules
from bot.game import creatures, eggs, teams
from bot.services.settling import settle_pending
from bot.storage.pokemon import as_document, new_id
from bot.storage.stores import Stores

DONE = "done"
NOT_STARTED = "not_started"
IN_TRADE = "in_trade"
NOT_ENOUGH = "not_enough"
FAILED = "failed"


@dataclass
class AdminResult:
    status: str
    grant: rules.Grant | None = None


async def _started(stores: Stores, trainer_id: int) -> dict | None:
    trainer = await stores.trainers.get(trainer_id)
    return trainer if trainer and trainer.get("first_partner_id") is not None else None


def _field_of(grant: rules.Grant) -> str:
    if grant.kind == rules.MONEY:
        return "money"
    if grant.kind == rules.EXP:
        return "exp_points"
    group = {rules.BALL: "balls", rules.ITEM: "items", rules.TM: "tms"}[grant.kind]
    return f"{group}.{grant.key}"


async def _add_pokemon(stores: Stores, trainer: dict, grant: rules.Grant) -> AdminResult:
    if trainer.get("trade_id"):
        return AdminResult(IN_TRADE, grant)
    trainer_id = trainer["_id"]
    creature = creatures.with_sort_fields(creatures.new_pokemon(int(grant.key), grant.amount))
    document = as_document(trainer_id, new_id(), creature)
    active = trainer["active_team"]
    has_room = len(trainer["teams"][str(active)]) < teams.TEAM_SIZE
    await stores.trainers.admin_add_pokemon(trainer_id, document, active if has_room else None)
    await settle_pending(stores, trainer_id)
    return AdminResult(DONE, grant)


async def add(stores: Stores, trainer_id: int, grant: rules.Grant) -> AdminResult:
    trainer = await _started(stores, trainer_id)
    if trainer is None:
        return AdminResult(NOT_STARTED, grant)
    if grant.kind == rules.POKEMON:
        return await _add_pokemon(stores, trainer, grant)
    if grant.kind == rules.EGG:
        now = datetime.now(timezone.utc)
        await stores.trainers.admin_add_eggs(trainer_id, [eggs.new_egg(new_id(), now) for _ in range(grant.amount)])
    elif grant.kind == rules.KEY_STONE:
        await stores.trainers.admin_set_key_stone(trainer_id, True)
    elif grant.kind == rules.STONE:
        await stores.trainers.admin_add_stone(trainer_id, grant.key)
    else:
        await stores.trainers.admin_increase(trainer_id, _field_of(grant), grant.amount)
    return AdminResult(DONE, grant)


async def remove(stores: Stores, trainer_id: int, grant: rules.Grant) -> AdminResult:
    if await _started(stores, trainer_id) is None:
        return AdminResult(NOT_STARTED, grant)
    if grant.kind in (rules.POKEMON, rules.EGG):
        return AdminResult(FAILED, grant)
    if grant.kind == rules.KEY_STONE:
        done = await stores.trainers.admin_set_key_stone(trainer_id, False)
    elif grant.kind == rules.STONE:
        done = await stores.trainers.admin_remove_stone(trainer_id, grant.key)
    else:
        done = await stores.trainers.admin_decrease(trainer_id, _field_of(grant), grant.amount)
    return AdminResult(DONE if done else NOT_ENOUGH, grant)
