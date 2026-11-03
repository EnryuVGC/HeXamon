from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.errors import DuplicateKeyError


class BanStore:
    def __init__(self, database: AsyncIOMotorDatabase):
        self._bans = database["bans"]

    async def ban(self, trainer_id: int) -> bool:
        try:
            await self._bans.insert_one({"_id": trainer_id, "banned_at": datetime.now(timezone.utc)})
        except DuplicateKeyError:
            return False
        return True

    async def unban(self, trainer_id: int) -> bool:
        result = await self._bans.delete_one({"_id": trainer_id})
        return result.deleted_count == 1

    async def is_banned(self, trainer_id: int) -> bool:
        return await self._bans.find_one({"_id": trainer_id}, {"_id": 1}) is not None
