from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.errors import DuplicateKeyError

OPEN = "open"
DONE = "done"


class LotteryStore:
    def __init__(self, database: AsyncIOMotorDatabase):
        self._draws = database["lottery_draws"]

    async def ensure_draw(self, day: str) -> None:
        try:
            await self._draws.update_one(
                {"_id": day},
                {"$setOnInsert": {"state": OPEN, "fees": 0}},
                upsert=True,
            )
        except DuplicateKeyError:
            pass

    async def get(self, day: str) -> dict | None:
        return await self._draws.find_one({"_id": day})

    async def add_fees(self, day: str, amount: int) -> None:
        await self._draws.update_one({"_id": day}, {"$inc": {"fees": amount}})

    async def latest_before(self, day: str) -> dict | None:
        return await self._draws.find_one({"_id": {"$lt": day}}, sort=[("_id", -1)])

    async def latest_done(self) -> dict | None:
        return await self._draws.find_one({"state": DONE}, sort=[("_id", -1)])

    async def oldest_open_before(self, day: str) -> dict | None:
        return await self._draws.find_one({"_id": {"$lt": day}, "state": OPEN}, sort=[("_id", 1)])

    async def set_carried(self, day: str, carried: int) -> None:
        try:
            await self._draws.update_one(
                {"_id": day},
                {"$set": {"carried": carried}, "$setOnInsert": {"state": OPEN, "fees": 0}},
                upsert=True,
            )
        except DuplicateKeyError:
            await self._draws.update_one({"_id": day}, {"$set": {"carried": carried}})

    async def finish(self, day: str, results: dict) -> bool:
        result = await self._draws.update_one(
            {"_id": day, "state": OPEN},
            {"$set": {**results, "state": DONE}},
        )
        return result.modified_count == 1
