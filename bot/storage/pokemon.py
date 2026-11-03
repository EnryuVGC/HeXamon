from datetime import datetime, timezone

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ASCENDING, DESCENDING, ReturnDocument
from pymongo.errors import DuplicateKeyError

from bot.game.sorting import SortOrder

APPLIED_REWARDS_KEPT = 20


def _sort_spec(order: SortOrder, reverse: bool = False) -> list[tuple[str, int]]:
    descending = order.descending != reverse
    direction = DESCENDING if descending else ASCENDING
    if order.field == "_id":
        return [("_id", direction)]
    return [(order.field, direction), ("_id", DESCENDING if reverse else ASCENDING)]


def _value_of(document: dict, field: str):
    if field.startswith("stats."):
        return document["stats"][int(field.split(".")[1])]
    return document[field]


def new_id() -> str:
    return str(ObjectId())


def as_document(trainer_id: int, pokemon_id: str, creature: dict) -> dict:
    return {
        **creature,
        "_id": ObjectId(pokemon_id),
        "trainer_id": trainer_id,
        "caught_at": datetime.now(timezone.utc),
    }


class PokemonStore:
    def __init__(self, database: AsyncIOMotorDatabase):
        self._pokemon = database["pokemon"]

    async def ensure_indexes(self) -> None:
        await self._pokemon.create_index(
            [("trainer_id", ASCENDING), ("_id", ASCENDING)],
            name="trainer_collection",
        )
        await self._pokemon.create_index(
            [("trainer_id", ASCENDING), ("level", DESCENDING), ("_id", ASCENDING)],
            name="trainer_by_level",
        )

    async def random_sample(self, trainer_id: int, matching: dict, size: int) -> list[dict]:
        pipeline = [{"$match": {"trainer_id": trainer_id, **matching}}, {"$sample": {"size": size}}]
        return await self._pokemon.aggregate(pipeline).to_list(size)

    async def by_ids(self, trainer_id: int, pokemon_ids: list[str]) -> dict:
        cursor = self._pokemon.find(
            {"_id": {"$in": [ObjectId(pokemon_id) for pokemon_id in pokemon_ids]}, "trainer_id": trainer_id}
        )
        return {str(document["_id"]): document async for document in cursor}

    def _candidates(self, trainer_id: int, excluded_ids: list[str], matching: dict | None = None) -> dict:
        match = {"trainer_id": trainer_id, **(matching or {})}
        if excluded_ids:
            match["_id"] = {"$nin": [ObjectId(pokemon_id) for pokemon_id in excluded_ids]}
        return match

    async def page_first(
        self,
        trainer_id: int,
        excluded_ids: list[str],
        order: SortOrder,
        limit: int,
        matching: dict | None = None,
    ) -> list[dict]:
        cursor = (
            self._pokemon.find(self._candidates(trainer_id, excluded_ids, matching))
            .sort(_sort_spec(order))
            .limit(limit)
            .allow_disk_use(True)
        )
        return await cursor.to_list(limit)

    def _from_anchor(self, match: dict, order: SortOrder, anchor: dict, forward: bool) -> dict:
        id_ascending = not order.descending if order.field == "_id" else True
        id_operator = ("$gte" if id_ascending else "$lte") if forward else ("$lt" if id_ascending else "$gt")
        if order.field == "_id":
            match["_id"] = {**match.get("_id", {}), id_operator: anchor["_id"]}
            return match
        value = _value_of(anchor, order.field)
        moves_up = order.descending != forward
        match["$or"] = [
            {order.field: {"$gt" if moves_up else "$lt": value}},
            {order.field: value, "_id": {id_operator: anchor["_id"]}},
        ]
        return match

    async def page_after(
        self,
        trainer_id: int,
        excluded_ids: list[str],
        order: SortOrder,
        anchor: dict,
        skip: int,
        limit: int,
        matching: dict | None = None,
    ) -> list[dict]:
        match = self._from_anchor(self._candidates(trainer_id, excluded_ids, matching), order, anchor, True)
        cursor = self._pokemon.find(match).sort(_sort_spec(order)).skip(skip).limit(limit).allow_disk_use(True)
        return await cursor.to_list(limit)

    async def page_before(
        self,
        trainer_id: int,
        excluded_ids: list[str],
        order: SortOrder,
        anchor: dict,
        skip: int,
        limit: int,
        matching: dict | None = None,
    ) -> list[dict]:
        match = self._from_anchor(self._candidates(trainer_id, excluded_ids, matching), order, anchor, False)
        cursor = (
            self._pokemon.find(match)
            .sort(_sort_spec(order, reverse=True))
            .skip(skip)
            .limit(limit)
            .allow_disk_use(True)
        )
        documents = await cursor.to_list(limit)
        documents.reverse()
        return documents

    async def get(self, trainer_id: int, pokemon_id: str) -> dict | None:
        return await self._pokemon.find_one({"_id": ObjectId(pokemon_id), "trainer_id": trainer_id})

    async def first_matching(self, trainer_id: int, matching: dict) -> dict | None:
        return await self._pokemon.find_one({"trainer_id": trainer_id, **matching})

    async def count_matching(self, trainer_id: int, matching: dict) -> int:
        return await self._pokemon.count_documents({"trainer_id": trainer_id, **matching})

    async def owned_names(self, trainer_id: int) -> list[str]:
        return await self._pokemon.distinct("name", {"trainer_id": trainer_id})

    async def owned_dex_ids(self, trainer_id: int) -> list[int]:
        return await self._pokemon.distinct("dex_id", {"trainer_id": trainer_id})

    async def insert_if_missing(self, document: dict) -> None:
        try:
            await self._pokemon.update_one(
                {"_id": document["_id"]},
                {"$setOnInsert": {k: v for k, v in document.items() if k != "_id"}},
                upsert=True,
            )
        except DuplicateKeyError:
            pass

    async def delete(self, trainer_id: int, pokemon_id: str) -> dict | None:
        return await self._pokemon.find_one_and_delete({"_id": ObjectId(pokemon_id), "trainer_id": trainer_id})

    async def transfer(self, from_trainer_id: int, to_trainer_id: int, pokemon_id: str, fields: dict) -> None:
        await self._pokemon.update_one(
            {"_id": ObjectId(pokemon_id), "trainer_id": from_trainer_id},
            {"$set": {**fields, "trainer_id": to_trainer_id}},
        )

    async def apply_progress(
        self,
        trainer_id: int,
        pokemon_id: str,
        reward_id: str,
        expected_exp: int | None,
        expected_evs: list[int] | None,
        fields: dict,
    ) -> bool:
        result = await self._pokemon.update_one(
            {
                "_id": ObjectId(pokemon_id),
                "trainer_id": trainer_id,
                "exp": expected_exp,
                "evs": expected_evs,
                "applied_rewards": {"$ne": reward_id},
            },
            {
                "$set": fields,
                "$push": {"applied_rewards": {"$each": [reward_id], "$slice": -APPLIED_REWARDS_KEPT}},
            },
        )
        return result.modified_count == 1

    async def replace_moves(self, trainer_id: int, pokemon_id: str, before: list[str], after: list[str]) -> bool:
        result = await self._pokemon.update_one(
            {"_id": ObjectId(pokemon_id), "trainer_id": trainer_id, "moves": before},
            {"$set": {"moves": after}},
        )
        return result.modified_count == 1

    async def evolve(self, trainer_id: int, pokemon_id: str, from_dex_id: int, fields: dict) -> bool:
        result = await self._pokemon.update_one(
            {"_id": ObjectId(pokemon_id), "trainer_id": trainer_id, "dex_id": from_dex_id},
            {"$set": fields},
        )
        return result.modified_count == 1

    async def set_evs(self, trainer_id: int, pokemon_id: str, before: list[int] | None, fields: dict) -> bool:
        result = await self._pokemon.update_one(
            {"_id": ObjectId(pokemon_id), "trainer_id": trainer_id, "evs": before},
            {"$set": fields},
        )
        return result.modified_count == 1

    async def apply_boost(
        self,
        trainer_id: int,
        pokemon_id: str,
        boost_id: str,
        stat: int,
        before: list[int],
        fields: dict,
    ) -> bool:
        result = await self._pokemon.update_one(
            {
                "_id": ObjectId(pokemon_id),
                "trainer_id": trainer_id,
                "ivs": before,
                f"boosts.{stat}": {"$exists": False},
            },
            {"$set": {**fields, f"boosts.{stat}": boost_id}},
        )
        return result.modified_count == 1

    async def set_nickname(self, trainer_id: int, pokemon_id: str, nickname: str) -> dict | None:
        return await self._pokemon.find_one_and_update(
            {"_id": ObjectId(pokemon_id), "trainer_id": trainer_id},
            {"$set": {"nickname": nickname, "name": nickname.casefold()}},
            return_document=ReturnDocument.AFTER,
        )
