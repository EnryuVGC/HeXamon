from datetime import datetime, timedelta, timezone

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ASCENDING, ReturnDocument

from bot.game import challenges as rules


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _older_than(seconds: int) -> dict:
    return {"$lt": _now() - timedelta(seconds=seconds)}


class ChallengeStore:
    def __init__(self, database: AsyncIOMotorDatabase):
        self._challenges = database["challenges"]

    async def ensure_indexes(self) -> None:
        await self._challenges.create_index(
            [("state", ASCENDING), ("updated_at", ASCENDING)],
            name="challenges_by_state",
        )
        await self._challenges.create_index(
            "finished_at",
            name="finished_challenges",
            expireAfterSeconds=rules.FINISHED_KEPT_SECONDS,
            sparse=True,
        )

    async def create(self, challenger: dict, target: dict, chat_id: int, settings: dict) -> str:
        result = await self._challenges.insert_one(
            {
                "state": rules.WAITING,
                rules.CHALLENGER: challenger,
                rules.TARGET: target,
                "settings": settings,
                "ready": [challenger["id"]],
                "chat_id": chat_id,
                "updated_at": _now(),
            }
        )
        return str(result.inserted_id)

    async def get(self, challenge_id: str) -> dict | None:
        return await self._challenges.find_one({"_id": ObjectId(challenge_id)})

    async def set_message(self, challenge_id: str, message_id: int) -> None:
        await self._challenges.update_one({"_id": ObjectId(challenge_id)}, {"$set": {"message_id": message_id}})

    async def _move(self, match: dict, fields: dict) -> dict | None:
        return await self._challenges.find_one_and_update(
            match,
            {"$set": {**fields, "updated_at": _now()}},
            return_document=ReturnDocument.AFTER,
        )

    async def set_setting(
        self,
        challenge_id: str,
        challenger_id: int,
        settings: dict,
        name: str,
        value: int | bool,
    ) -> dict | None:
        return await self._move(
            {"_id": ObjectId(challenge_id), "state": rules.WAITING, "settings": settings},
            {f"settings.{name}": value, "ready": [challenger_id]},
        )

    async def mark_ready(self, challenge_id: str, trainer_id: int) -> dict | None:
        return await self._challenges.find_one_and_update(
            {"_id": ObjectId(challenge_id), "state": rules.WAITING, "ready": {"$ne": trainer_id}},
            {"$addToSet": {"ready": trainer_id}, "$set": {"updated_at": _now()}},
            return_document=ReturnDocument.AFTER,
        )

    async def unmark_ready(self, challenge_id: str, trainer_id: int) -> dict | None:
        return await self._challenges.find_one_and_update(
            {"_id": ObjectId(challenge_id), "state": rules.WAITING, "ready": trainer_id},
            {"$pull": {"ready": trainer_id}, "$set": {"updated_at": _now()}},
            return_document=ReturnDocument.AFTER,
        )

    async def begin_joining(self, challenge_id: str) -> dict | None:
        return await self._move(
            {"_id": ObjectId(challenge_id), "state": rules.WAITING, "ready.1": {"$exists": True}},
            {"state": rules.JOINING},
        )

    async def reopen(self, challenge_id: str, challenger_id: int) -> None:
        await self._move(
            {"_id": ObjectId(challenge_id), "state": rules.JOINING},
            {"state": rules.WAITING, "ready": [challenger_id]},
        )

    async def start_battle(self, challenge_id: str, sides: dict, current: str) -> dict | None:
        fields = {
            f"{side}.{name}": value
            for side, battle_side in sides.items()
            for name, value in battle_side.items()
        }
        return await self._move(
            {"_id": ObjectId(challenge_id), "state": rules.JOINING},
            {
                **fields,
                "state": rules.BATTLING,
                "current": current,
                "phase": rules.MOVE,
                "turn": 0,
                "draw_offers": [],
            },
        )

    async def advance(self, challenge_id: str, turn: int, fields: dict, rewards: dict | None = None) -> dict | None:
        update = {"$set": {**fields, "draw_offers": [], "updated_at": _now()}, "$inc": {"turn": 1}}
        if rewards:
            update["$push"] = {f"{side}.rewards": {"$each": queued} for side, queued in rewards.items()}
        return await self._challenges.find_one_and_update(
            {"_id": ObjectId(challenge_id), "state": rules.BATTLING, "turn": turn},
            update,
            return_document=ReturnDocument.AFTER,
        )

    async def change_form(self, challenge_id: str, turn: int, side: str, slot: int, form_id: int) -> dict | None:
        return await self._move(
            {
                "_id": ObjectId(challenge_id),
                "state": rules.BATTLING,
                "turn": turn,
                "current": side,
                "phase": rules.MOVE,
                f"{side}.active": slot,
                f"{side}.form_used": {"$ne": True},
            },
            {f"{side}.team.{slot}.pokemon.form_id": form_id, f"{side}.form_used": True},
        )

    async def grow_team(self, challenge_id: str, turn: int, fields: dict, raised: dict) -> dict | None:
        update = {"$set": fields}
        if raised:
            update["$inc"] = raised
        return await self._challenges.find_one_and_update(
            {"_id": ObjectId(challenge_id), "state": rules.BATTLING, "turn": turn},
            update,
            return_document=ReturnDocument.AFTER,
        )

    async def offer_draw(self, challenge_id: str, trainer_id: int) -> dict | None:
        return await self._challenges.find_one_and_update(
            {
                "_id": ObjectId(challenge_id),
                "state": rules.BATTLING,
                "$or": [{f"{side}.id": trainer_id} for side in rules.SIDES],
            },
            {"$addToSet": {"draw_offers": trainer_id}},
            return_document=ReturnDocument.AFTER,
        )

    async def close_as_draw(self, challenge_id: str) -> dict | None:
        return await self._move(
            {"_id": ObjectId(challenge_id), "state": rules.BATTLING, "draw_offers.1": {"$exists": True}},
            {"state": rules.SETTLING, "outcome": rules.DRAWN},
        )

    async def finish(self, challenge_id: str, paid_prize: int | None = None) -> dict | None:
        paid = {} if paid_prize is None else {"paid_prize": paid_prize}
        return await self._move(
            {"_id": ObjectId(challenge_id), "state": rules.SETTLING},
            {"state": rules.DONE, "finished_at": _now(), **paid},
        )

    async def claim_expired(self) -> dict | None:
        expired = await self._move(
            {
                "state": {"$in": [rules.WAITING, rules.JOINING]},
                "updated_at": _older_than(rules.WAITING_SECONDS),
            },
            {"state": rules.SETTLING, "outcome": rules.EXPIRED},
        )
        if expired is not None:
            return expired
        for side in rules.SIDES:
            timed_out = await self._move(
                {
                    "state": rules.BATTLING,
                    "current": side,
                    "updated_at": _older_than(rules.TURN_SECONDS),
                },
                {"state": rules.SETTLING, "outcome": rules.TIMED_OUT, "loser": side},
            )
            if timed_out is not None:
                return timed_out
        return None

    async def claim_unfinished(self) -> dict | None:
        return await self._move(
            {"state": rules.SETTLING, "updated_at": _older_than(rules.RETRY_SECONDS)},
            {},
        )
