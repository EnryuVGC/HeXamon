from dataclasses import dataclass
from datetime import datetime, timezone

from bot.game import store as rules
from bot.storage.stores import Stores

DONE = "done"
BAD_FORMAT = "bad_format"
NO_MONEY = "no_money"
NOT_ENOUGH = "not_enough"
KEY_STONE_OWNED = "key_stone_owned"
KEY_STONE_SINGLE = "key_stone_single"
KEY_STONE_NO_SELL = "key_stone_no_sell"


@dataclass
class Order:
    status: str
    good: rules.Good | None = None
    amount: int = 0
    total: int = 0


async def available_tms(stores: Stores, trainer_id: int) -> list[int]:
    trainer = await stores.trainers.get(trainer_id) or {}
    return rules.available_tms(trainer_id, trainer, datetime.now(timezone.utc).date())


async def _buy_key_stone(stores: Stores, trainer_id: int, good: rules.Good, amount: int) -> Order:
    if amount != 1:
        return Order(KEY_STONE_SINGLE)
    cost = rules.price_of(good.price_key)
    if await stores.trainers.buy_key_stone(trainer_id, cost):
        return Order(DONE, good, amount, cost)
    owned = await stores.trainers.has_key_stone(trainer_id)
    return Order(KEY_STONE_OWNED if owned else NO_MONEY)


async def buy(stores: Stores, trainer_id: int, args: str | None) -> Order:
    order = rules.parse_order(args)
    if order is None:
        return Order(BAD_FORMAT)
    good, amount = order
    if good.key == rules.KEY_STONE:
        return await _buy_key_stone(stores, trainer_id, good, amount)
    cost = rules.price_of(good.price_key) * amount
    if not await stores.trainers.buy_goods(trainer_id, good.field, amount, cost):
        return Order(NO_MONEY)
    return Order(DONE, good, amount, cost)


async def sell(stores: Stores, trainer_id: int, args: str | None) -> Order:
    order = rules.parse_order(args)
    if order is None:
        return Order(BAD_FORMAT)
    good, amount = order
    if good.key == rules.KEY_STONE:
        return Order(KEY_STONE_NO_SELL)
    gain = rules.sell_price_of(good) * amount
    if not await stores.trainers.sell_goods(trainer_id, good.field, amount, gain):
        return Order(NOT_ENOUGH)
    return Order(DONE, good, amount, gain)
