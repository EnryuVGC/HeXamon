from dataclasses import dataclass
from datetime import date, datetime, timezone

from bot.game import pokedex, store, tms as rules
from bot.game.display import choice_of
from bot.game.encounters import BATTLE_IDLE_SECONDS
from bot.game.paging import page_size_of
from bot.game.sorting import SortOrder, order_for
from bot.services import pokemon_list
from bot.services.collection import sort_of
from bot.services.pokemon_list import PokemonPage
from bot.services.settling import apply_teaching, settle_pending
from bot.storage.pokemon import new_id
from bot.storage.stores import Stores

BOUGHT = "bought"
NOT_IN_STORE = "not_in_store"
NO_MONEY = "no_money"
TAUGHT = "taught"
NEEDS_FORGET = "needs_forget"
CANNOT_LEARN = "cannot_learn"
NO_TM = "no_tm"
GONE = "gone"
IN_BATTLE = "in_battle"
IN_TRADE = "in_trade"
FAILED = "failed"


@dataclass
class TmCard:
    number: int
    move: str
    owned: bool
    in_store: bool
    buy_price: int
    sell_price: int


@dataclass
class TeachResult:
    status: str
    move: str
    pokemon: dict | None = None
    forgotten: str | None = None


def _today() -> date:
    return datetime.now(timezone.utc).date()


def _in_store(trainer_id: int, trainer: dict, number: int) -> bool:
    return number in store.available_tms(trainer_id, trainer, _today())


def _learners(move: str) -> dict:
    return {"dex_id": {"$in": list(rules.learner_ids(move))}, "moves": {"$ne": move}}


def _order(trainer: dict) -> SortOrder:
    sort = sort_of(trainer)
    return order_for(sort.key, sort.direction)


async def _load(stores: Stores, trainer_id: int) -> dict | None:
    trainer = await stores.trainers.get(trainer_id)
    if not trainer or trainer.get("first_partner_id") is None:
        return None
    await settle_pending(stores, trainer_id, trainer)
    return await stores.trainers.get(trainer_id)


async def card(stores: Stores, trainer_id: int, number: int) -> TmCard | None:
    move = rules.move_of(number)
    trainer = await stores.trainers.get(trainer_id)
    if move is None or trainer is None:
        return None
    in_store = _in_store(trainer_id, trainer, number)
    return TmCard(
        number,
        move,
        trainer.get("tms", {}).get(str(number), 0) > 0,
        in_store,
        store.tm_price(move),
        rules.sell_price(move, in_store),
    )


async def buy(stores: Stores, trainer_id: int, number: int) -> tuple[str, int]:
    move = rules.move_of(number)
    trainer = await stores.trainers.get(trainer_id)
    if move is None or trainer is None or not _in_store(trainer_id, trainer, number):
        return NOT_IN_STORE, 0
    price = store.tm_price(move)
    purchase = store.tm_purchase(number, _today())
    if await stores.trainers.buy_tm(trainer_id, str(number), price, purchase, store.WEEKLY_TM_COUNT):
        return BOUGHT, price
    trainer = await stores.trainers.get(trainer_id)
    if trainer is None or not _in_store(trainer_id, trainer, number):
        return NOT_IN_STORE, 0
    return NO_MONEY, price


async def sell(stores: Stores, trainer_id: int, number: int) -> int | None:
    move = rules.move_of(number)
    trainer = await stores.trainers.get(trainer_id)
    if move is None or trainer is None:
        return None
    price = rules.sell_price(move, _in_store(trainer_id, trainer, number))
    return price if await stores.trainers.sell_tm(trainer_id, str(number), price) else None


async def first_learners_page(stores: Stores, trainer_id: int, number: int) -> PokemonPage | None:
    move = rules.move_of(number)
    trainer = await _load(stores, trainer_id)
    if move is None or trainer is None:
        return None
    matching = _learners(move)
    total = await stores.pokemon.count_matching(trainer_id, matching)
    page = await pokemon_list.first_page(
        stores, trainer_id, [], total, _order(trainer), page_size_of(trainer), matching
    )
    page.display = choice_of(trainer)
    return page


async def turn_learners_page(
    stores: Stores,
    trainer_id: int,
    number: int,
    page: int,
    delta: int,
    anchor_id: str,
) -> PokemonPage | None:
    move = rules.move_of(number)
    trainer = await _load(stores, trainer_id)
    if move is None or trainer is None:
        return None
    matching = _learners(move)
    total = await stores.pokemon.count_matching(trainer_id, matching)
    result = await pokemon_list.turn_page(
        stores, trainer_id, [], total, page, delta, anchor_id, _order(trainer), page_size_of(trainer), matching
    )
    result.display = choice_of(trainer)
    return result


async def owns(stores: Stores, trainer_id: int, number: int) -> bool:
    trainer = await stores.trainers.get(trainer_id)
    return bool(trainer) and trainer.get("tms", {}).get(str(number), 0) > 0


async def teach(
    stores: Stores,
    trainer_id: int,
    number: int,
    pokemon_id: str,
    forgotten: int | None = None,
) -> TeachResult:
    move = rules.move_of(number)
    if move is None or await _load(stores, trainer_id) is None:
        return TeachResult(GONE, move or "")
    pokemon = await stores.pokemon.get(trainer_id, pokemon_id)
    if pokemon is None:
        return TeachResult(GONE, move)
    moves = pokemon["moves"]
    if pokemon["dex_id"] not in rules.learner_ids(move) or move in moves:
        return TeachResult(CANNOT_LEARN, move, pokemon)
    if forgotten is None and len(moves) >= pokedex.MAX_MOVES:
        return TeachResult(NEEDS_FORGET, move, pokemon)
    if forgotten is not None and not 0 <= forgotten < len(moves):
        return TeachResult(CANNOT_LEARN, move, pokemon)

    teaching = {
        "id": new_id(),
        "pokemon_id": pokemon_id,
        "tm": str(number),
        "before": moves,
        "after": rules.after_teaching(moves, move, forgotten),
    }
    if not await stores.trainers.begin_teaching(trainer_id, teaching, BATTLE_IDLE_SECONDS):
        return await _refusal(stores, trainer_id, number, move, pokemon)
    if not await apply_teaching(stores, trainer_id, teaching):
        return TeachResult(FAILED, move, pokemon)
    return TeachResult(TAUGHT, move, pokemon, moves[forgotten] if forgotten is not None else None)


async def _refusal(stores: Stores, trainer_id: int, number: int, move: str, pokemon: dict) -> TeachResult:
    if await stores.trainers.in_trade(trainer_id):
        return TeachResult(IN_TRADE, move, pokemon)
    if await stores.trainers.in_battle(trainer_id, BATTLE_IDLE_SECONDS):
        return TeachResult(IN_BATTLE, move, pokemon)
    if not await owns(stores, trainer_id, number):
        return TeachResult(NO_TM, move, pokemon)
    return TeachResult(FAILED, move, pokemon)
