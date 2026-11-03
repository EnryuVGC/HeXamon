from dataclasses import dataclass, field

from bot.game import creatures
from bot.game import trades as rules
from bot.game.encounters import BATTLE_IDLE_SECONDS
from bot.game.teams import TEAM_SIZE, team_numbers
from bot.services import collection
from bot.services.collection import CollectionPage
from bot.services.settling import settle_pending
from bot.storage.stores import Stores

REQUESTED = "requested"
PARTNER_NOT_STARTED = "partner_not_started"
YOU_IN_BATTLE = "you_in_battle"
YOU_IN_TRADE = "you_in_trade"
PARTNER_IN_BATTLE = "partner_in_battle"
PARTNER_IN_TRADE = "partner_in_trade"

WAITING = "waiting"
ALREADY_ACCEPTED = "already_accepted"
FINISHED = "finished"
ENDED = "ended"


@dataclass
class TradeRequest:
    status: str
    trade_id: str | None = None


@dataclass
class Agreement:
    trade: dict | None
    fled: list[dict] = field(default_factory=list)
    blocked: str | None = None


@dataclass
class Choice:
    trade: dict | None
    hatched: bool = False


@dataclass
class Acceptance:
    status: str
    trade: dict | None = None


async def _is_in_trade(stores: Stores, trainer_id: int) -> bool | None:
    await settle_pending(stores, trainer_id)
    if await stores.trainers.can_trade(trainer_id, BATTLE_IDLE_SECONDS):
        return None
    return await stores.trainers.in_trade(trainer_id)


async def _blocked_status(stores: Stores, your_id: int, other_id: int) -> str | None:
    in_trade = await _is_in_trade(stores, your_id)
    if in_trade is not None:
        return YOU_IN_TRADE if in_trade else YOU_IN_BATTLE
    in_trade = await _is_in_trade(stores, other_id)
    if in_trade is not None:
        return PARTNER_IN_TRADE if in_trade else PARTNER_IN_BATTLE
    return None


async def request(
    stores: Stores,
    requester_id: int,
    requester_name: str,
    partner_id: int,
    partner_name: str,
    chat_id: int,
) -> TradeRequest:
    if not await stores.trainers.has_started(partner_id):
        return TradeRequest(PARTNER_NOT_STARTED)
    blocked = await _blocked_status(stores, requester_id, partner_id)
    if blocked is not None:
        return TradeRequest(blocked)
    trade_id = await stores.trades.create(
        rules.side_of(requester_name, requester_id),
        rules.side_of(partner_name, partner_id),
        chat_id,
    )
    return TradeRequest(REQUESTED, trade_id)


async def remember_message(stores: Stores, trade_id: str, message_id: int) -> None:
    await stores.trades.set_message(trade_id, message_id)


async def get(stores: Stores, trade_id: str) -> dict | None:
    return await stores.trades.get(trade_id)


async def current_of(stores: Stores, trainer_id: int) -> dict | None:
    trainer = await stores.trainers.get(trainer_id)
    trade_id = trainer.get("trade_id") if trainer else None
    return await stores.trades.get(trade_id) if trade_id else None


async def agree(stores: Stores, trade: dict, partner_id: int) -> Agreement:
    trade_id = str(trade["_id"])
    requester_id = trade[rules.REQUESTER]["id"]
    blocked = await _blocked_status(stores, partner_id, requester_id)
    if blocked is not None:
        return Agreement(None, blocked=blocked)
    if await stores.trades.agree(trade_id, partner_id) is None:
        return Agreement(None)
    fled = []
    for side in rules.SIDES:
        joined = await stores.trainers.join_trade(trade[side]["id"], trade_id, BATTLE_IDLE_SECONDS)
        if joined is None:
            for joined_side in rules.SIDES:
                await stores.trainers.leave_trade(trade[joined_side]["id"], trade_id)
            await stores.trades.reopen(trade_id)
            blocked = await _blocked_status(stores, partner_id, requester_id)
            return Agreement(None, fled, blocked or YOU_IN_BATTLE)
        if "encounter" in joined:
            fled.append(joined["encounter"])
    return Agreement(await stores.trades.start_choosing(trade_id), fled)


async def chooser_page(stores: Stores, trade: dict) -> CollectionPage | None:
    return await collection.first_page(stores, rules.chooser_id(trade))


async def turn_chooser_page(
    stores: Stores,
    trade: dict,
    page: int,
    delta: int,
    anchor_id: str,
) -> CollectionPage | None:
    await stores.trades.touch(str(trade["_id"]))
    return await collection.turn_page(stores, rules.chooser_id(trade), page, delta, anchor_id)


async def choose(stores: Stores, trade: dict, trainer_id: int, pokemon_id: str) -> Choice:
    pokemon = await stores.pokemon.get(trainer_id, pokemon_id)
    if pokemon is None:
        return Choice(None)
    if pokemon.get("egg"):
        return Choice(None, hatched=True)
    return Choice(await stores.trades.choose(str(trade["_id"]), trade["state"], trainer_id, rules.offer_of(pokemon)))


async def offered_pokemon(stores: Stores, trade: dict) -> list[dict] | None:
    offered = []
    for side in rules.SIDES:
        pokemon = await stores.pokemon.get(trade[side]["id"], trade[side]["offer"]["pokemon_id"])
        if pokemon is None:
            return None
        offered.append(pokemon)
    return offered


async def accept(stores: Stores, trade_id: str, trainer_id: int) -> Acceptance:
    trade = await stores.trades.accept(trade_id, trainer_id)
    if trade is None:
        current = await stores.trades.get(trade_id)
        return Acceptance(ALREADY_ACCEPTED if current and current["state"] == rules.CONFIRMING else ENDED)
    swapping = await stores.trades.begin_swap(trade_id)
    if swapping is None:
        return Acceptance(WAITING)
    return Acceptance(FINISHED, await settle(stores, swapping))


async def cancel(stores: Stores, trade_id: str) -> dict | None:
    closing = await stores.trades.close(trade_id, rules.CANCELLED)
    return await settle(stores, closing) if closing else None


async def _swap(stores: Stores, trade: dict) -> None:
    trade_id = str(trade["_id"])
    requester, partner = trade[rules.REQUESTER], trade[rules.PARTNER]
    pairs = ((requester, partner), (partner, requester))
    for giver, taker in pairs:
        await stores.trainers.hand_over(
            giver["id"],
            trade_id,
            giver["offer"]["pokemon_id"],
            taker["offer"]["dex_id"],
            list(team_numbers()),
        )
    for giver, taker in pairs:
        offer = giver["offer"]
        await stores.pokemon.transfer(giver["id"], taker["id"], offer["pokemon_id"], creatures.after_trade(offer["dex_id"]))
    for giver, taker in pairs:
        await stores.trainers.receive_traded(taker["id"], trade_id, giver["offer"]["pokemon_id"], TEAM_SIZE)


async def settle(stores: Stores, trade: dict) -> dict | None:
    trade_id = str(trade["_id"])
    if trade["state"] == rules.SWAPPING:
        await _swap(stores, trade)
        finished = await stores.trades.finish(trade_id, rules.SWAPPING, rules.DONE)
    elif trade["state"] == rules.CLOSING:
        for side in rules.SIDES:
            await stores.trainers.leave_trade(trade[side]["id"], trade_id)
        finished = await stores.trades.finish(trade_id, rules.CLOSING, rules.CLOSED)
    else:
        return trade
    return finished or await stores.trades.get(trade_id)


async def next_settled(stores: Stores) -> dict | None:
    trade = await stores.trades.claim_unfinished() or await stores.trades.claim_expired()
    return await settle(stores, trade) if trade else None
