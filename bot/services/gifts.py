from bot.game import gifts as rules
from bot.services.settling import apply_gift
from bot.storage.pokemon import new_id
from bot.storage.stores import Stores

SENT = "sent"
BAD_AMOUNT = "bad_amount"
NOT_STARTED = "not_started"
NO_MONEY = "no_money"


async def give(stores: Stores, sender_id: int, receiver_id: int, args: str | None) -> str:
    amount = rules.parse_amount(args)
    if amount is None:
        return BAD_AMOUNT
    if not await stores.trainers.has_started(receiver_id):
        return NOT_STARTED
    gift = {"id": new_id(), "to": receiver_id, "amount": amount}
    if not await stores.trainers.begin_gift(sender_id, gift):
        return NO_MONEY
    await apply_gift(stores, sender_id, gift)
    return SENT
