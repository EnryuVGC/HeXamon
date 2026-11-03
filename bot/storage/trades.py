from datetime import datetime, timedelta, timezone

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ASCENDING, ReturnDocument

from bot.game import trades as rules


def _now() -> datetime:
    return datetime.now(timezone.utc)


class TradeStore:
    def __init__(self, database: AsyncIOMotorDatabase):
        self._trades = database["trades"]

    async def ensure_indexes(self) -> None:
        await self._trades.create_index(
            [("state", ASCENDING), ("updated_at", ASCENDING)],
            name="trades_by_state",
        )
        await self._trades.create_index(
            "finished_at",
            name="finished_trades",
            expireAfterSeconds=rules.FINISHED_KEPT_SECONDS,
            sparse=True,
        )

    async def create(self, requester: dict, partner: dict, chat_id: int) -> str:
        result = await self._trades.insert_one(
            {
                "state": rules.REQUESTED,
                rules.REQUESTER: requester,
                rules.PARTNER: partner,
                "accepted": [],
                "chat_id": chat_id,
                "updated_at": _now(),
            }
        )
        return str(result.inserted_id)

    async def get(self, trade_id: str) -> dict | None:
        return await self._trades.find_one({"_id": ObjectId(trade_id)})

    async def set_message(self, trade_id: str, message_id: int) -> None:
        await self._trades.update_one({"_id": ObjectId(trade_id)}, {"$set": {"message_id": message_id}})

    async def touch(self, trade_id: str) -> None:
        await self._trades.update_one(
            {"_id": ObjectId(trade_id), "state": {"$in": rules.ACTIVE_STATES}},
            {"$set": {"updated_at": _now()}},
        )

    async def _move(self, match: dict, fields: dict) -> dict | None:
        return await self._trades.find_one_and_update(
            match,
            {"$set": {**fields, "updated_at": _now()}},
            return_document=ReturnDocument.AFTER,
        )

    async def agree(self, trade_id: str, partner_id: int) -> dict | None:
        return await self._move(
            {"_id": ObjectId(trade_id), "state": rules.REQUESTED, f"{rules.PARTNER}.id": partner_id},
            {"state": rules.JOINING},
        )

    async def reopen(self, trade_id: str) -> None:
        await self._move(
            {"_id": ObjectId(trade_id), "state": rules.JOINING},
            {"state": rules.REQUESTED},
        )

    async def start_choosing(self, trade_id: str) -> dict | None:
        return await self._move(
            {"_id": ObjectId(trade_id), "state": rules.JOINING},
            {"state": rules.CHOOSING_REQUESTER},
        )

    async def choose(self, trade_id: str, state: str, trainer_id: int, offer: dict) -> dict | None:
        side = rules.CHOOSER_SIDE[state]
        return await self._move(
            {"_id": ObjectId(trade_id), "state": state, f"{side}.id": trainer_id},
            {"state": rules.STATE_AFTER_CHOICE[state], f"{side}.offer": offer},
        )

    async def accept(self, trade_id: str, trainer_id: int) -> dict | None:
        return await self._trades.find_one_and_update(
            {
                "_id": ObjectId(trade_id),
                "state": rules.CONFIRMING,
                "accepted": {"$ne": trainer_id},
                "$or": [{f"{side}.id": trainer_id} for side in rules.SIDES],
            },
            {"$addToSet": {"accepted": trainer_id}, "$set": {"updated_at": _now()}},
            return_document=ReturnDocument.AFTER,
        )

    async def begin_swap(self, trade_id: str) -> dict | None:
        return await self._move(
            {"_id": ObjectId(trade_id), "state": rules.CONFIRMING, "accepted.1": {"$exists": True}},
            {"state": rules.SWAPPING},
        )

    async def close(self, trade_id: str, outcome: str) -> dict | None:
        return await self._move(
            {"_id": ObjectId(trade_id), "state": {"$in": rules.ACTIVE_STATES}},
            {"state": rules.CLOSING, "outcome": outcome},
        )

    async def finish(self, trade_id: str, from_state: str, to_state: str) -> dict | None:
        return await self._move(
            {"_id": ObjectId(trade_id), "state": from_state},
            {"state": to_state, "finished_at": _now()},
        )

    async def claim_expired(self) -> dict | None:
        return await self._move(
            {
                "state": {"$in": rules.ACTIVE_STATES},
                "updated_at": {"$lt": _now() - timedelta(seconds=rules.IDLE_SECONDS)},
            },
            {"state": rules.CLOSING, "outcome": rules.EXPIRED},
        )

    async def claim_unfinished(self) -> dict | None:
        return await self._move(
            {
                "state": {"$in": rules.UNFINISHED_STATES},
                "updated_at": {"$lt": _now() - timedelta(seconds=rules.RETRY_SECONDS)},
            },
            {},
        )
