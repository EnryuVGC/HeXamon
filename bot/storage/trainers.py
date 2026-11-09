from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from bot.game import earnings
from bot.game.challenges import Payout

APPLIED_GIFTS_KEPT = 50
APPLIED_REFERRALS_KEPT = 50
EARNING_ATTEMPTS = 5


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _earned_exp(rewards: list[dict]) -> int:
    return sum(reward["exp"] for reward in rewards)


def _with_money(update: dict, paid: int, fields: dict) -> dict:
    if not paid:
        return update
    return {
        **update,
        "$inc": {**update.get("$inc", {}), "money": paid},
        "$set": {**update.get("$set", {}), **fields},
    }


def _not_in_battle_or_trade(idle_seconds: int) -> dict:
    return {
        "trade_id": {"$exists": False},
        "challenge_id": {"$exists": False},
        "$or": [
            {"encounter.state": {"$ne": "battling"}},
            {"encounter.updated_at": {"$lt": _now() - timedelta(seconds=idle_seconds)}},
        ]
    }


def _pokemon_left() -> dict:
    return {"$subtract": ["$pokemon_count", {"$size": {"$ifNull": ["$pending_releases", []]}}]}


class TrainerStore:
    def __init__(self, database: AsyncIOMotorDatabase):
        self._trainers = database["trainers"]
        self._migrations = database["migrations"]

    async def ensure_indexes(self) -> None:
        await self._trainers.create_index("encounter.updated_at", name="idle_encounters", sparse=True)
        await self._trainers.create_index("move_prompts.expires_at", name="expiring_move_prompts", sparse=True)
        await self._trainers.create_index(
            "exp_points",
            name="unpaid_referrals",
            partialFilterExpression={"referred_by.id": {"$exists": True}},
        )
        await self._trainers.create_index("lottery.day", name="lottery_players", sparse=True)
        await self._trainers.create_index("eggs.hatch_at", name="hatching_eggs", sparse=True)

    async def get(self, trainer_id: int) -> dict | None:
        return await self._trainers.find_one({"_id": trainer_id})

    async def migration_done(self, name: str) -> bool:
        return await self._migrations.count_documents({"_id": name}, limit=1) == 1

    async def finish_migration(self, name: str) -> None:
        await self._migrations.update_one({"_id": name}, {"$set": {"finished_at": _now()}}, upsert=True)

    async def tm_owners_to_renumber(self) -> AsyncIterator[int]:
        async for trainer in self._trainers.find({"tms": {"$exists": True}, "tms_renumbered": {"$ne": True}}, {"_id": 1}):
            yield trainer["_id"]

    async def renumber_tms(self, trainer_id: int, before: dict, tms: dict) -> bool:
        result = await self._trainers.update_one(
            {
                "_id": trainer_id,
                "tms": before,
                "tms_renumbered": {"$ne": True},
                "pending_teachings.0": {"$exists": False},
            },
            {"$set": {"tms": tms, "tms_renumbered": True}},
        )
        return result.modified_count == 1

    async def has_started(self, trainer_id: int) -> bool:
        match = {"_id": trainer_id, "first_partner_id": {"$ne": None}}
        return await self._trainers.count_documents(match, limit=1) == 1

    async def register(self, trainer_id: int, region: str, balls: dict) -> dict:
        try:
            return await self._trainers.find_one_and_update(
                {"_id": trainer_id},
                {
                    "$setOnInsert": {
                        "first_partner_id": None,
                        "region": region,
                        "balls": balls,
                        "caught_dex": [],
                        "seen_dex": [],
                        "pending_pokemon": [],
                        "pokemon_count": 0,
                        "created_at": _now(),
                    }
                },
                upsert=True,
                return_document=ReturnDocument.AFTER,
            )
        except DuplicateKeyError:
            return await self.get(trainer_id)

    async def claim_first_partner(
        self,
        trainer_id: int,
        document: dict,
        region: str,
        balls: dict,
        teams: dict,
        money: int,
    ) -> bool:
        now = _now()
        try:
            await self._trainers.find_one_and_update(
                {"_id": trainer_id, "first_partner_id": None},
                {
                    "$set": {
                        "first_partner_id": document["dex_id"],
                        "first_partner_chosen_at": now,
                        "teams": teams,
                        "active_team": 1,
                    },
                    "$inc": {"pokemon_count": 1, "money": money},
                    "$push": {"pending_pokemon": document},
                    "$addToSet": {"caught_dex": document["dex_id"]},
                    "$setOnInsert": {"region": region, "balls": balls, "created_at": now},
                },
                upsert=True,
            )
        except DuplicateKeyError:
            return False
        return True

    async def set_referrer(self, trainer_id: int, referrer_id: int, name: str) -> bool:
        result = await self._trainers.update_one(
            {"_id": trainer_id, "first_partner_id": None, "referred_by": {"$exists": False}},
            {"$set": {"referred_by": {"id": referrer_id, "name": name}}},
        )
        return result.modified_count == 1

    async def next_unpaid_referral(self, target_exp: int) -> dict | None:
        return await self._trainers.find_one(
            {"exp_points": {"$gte": target_exp}, "referred_by.id": {"$exists": True}},
            projection={"referred_by": 1},
        )

    async def clear_referrer(self, trainer_id: int) -> None:
        await self._trainers.update_one({"_id": trainer_id}, {"$unset": {"referred_by": ""}})

    async def pay_referral(
        self,
        referrer_id: int,
        invited_id: int,
        count: int,
        counters: dict[str, int],
        stone: str | None,
    ) -> int | None:
        others = {field: amount for field, amount in counters.items() if field != "money"}
        update = {
            "$inc": {"referral_count": 1, **others},
            "$push": {"applied_referrals": {"$each": [invited_id], "$slice": -APPLIED_REFERRALS_KEPT}},
        }
        if stone is not None:
            update["$addToSet"] = {"mega_stones": stone}

        async def write(paid: int, guard: dict, fields: dict) -> bool:
            result = await self._trainers.update_one(
                {
                    "_id": referrer_id,
                    "referral_count": count or None,
                    "applied_referrals": {"$ne": invited_id},
                    **guard,
                },
                _with_money(update, paid, fields),
            )
            return result.modified_count == 1

        return await self._paying(referrer_id, counters.get("money", 0), write)

    async def buy_lottery_ticket(self, trainer_id: int, day: str, ticket: dict, max_entries: int) -> bool:
        result = await self._trainers.update_one(
            {
                "_id": trainer_id,
                "first_partner_id": {"$ne": None},
                "money": {"$gte": ticket["cost"]},
                "lottery.tickets.numbers": {"$ne": ticket["numbers"]},
                "$or": [
                    {"lottery": {"$exists": False}},
                    {"lottery.day": day, f"lottery.tickets.{max_entries - 1}": {"$exists": False}},
                ],
            },
            {
                "$inc": {"money": -ticket["cost"]},
                "$set": {"lottery.day": day},
                "$push": {"lottery.tickets": ticket},
            },
        )
        return result.modified_count == 1

    async def lottery_totals(self, day: str, numbers: list[int]) -> tuple[int, dict[int, int]]:
        cursor = self._trainers.aggregate(
            [
                {"$match": {"lottery.day": day}},
                {"$unwind": "$lottery.tickets"},
                {
                    "$group": {
                        "_id": {"$size": {"$setIntersection": ["$lottery.tickets.numbers", numbers]}},
                        "entries": {"$sum": 1},
                        "fees": {"$sum": "$lottery.tickets.cost"},
                    }
                },
            ]
        )
        groups = await cursor.to_list(None)
        return sum(group["fees"] for group in groups), {group["_id"]: group["entries"] for group in groups}

    async def next_lottery_player(self, today: str) -> dict | None:
        return await self._trainers.find_one(
            {"lottery.day": {"$lt": today}},
            projection={"lottery": 1, "mega_stones": 1},
        )

    async def pay_lottery_player(
        self,
        trainer_id: int,
        lottery: dict,
        counters: dict[str, int],
        key_items: list[str],
    ) -> int | None:
        update = {"$set": {"last_lottery": lottery}, "$unset": {"lottery": ""}}
        others = {field: amount for field, amount in counters.items() if field != "money"}
        if others:
            update["$inc"] = others
        if key_items:
            update["$addToSet"] = {"mega_stones": {"$each": key_items}}

        async def write(paid: int, guard: dict, fields: dict) -> bool:
            result = await self._trainers.update_one(
                {"_id": trainer_id, "lottery.day": lottery["day"], **guard},
                _with_money(update, paid, fields),
            )
            return result.modified_count == 1

        return await self._paying(trainer_id, counters.get("money", 0), write)

    async def set_pokemon_sort_key(self, trainer_id: int, key: str) -> None:
        await self._trainers.update_one({"_id": trainer_id}, {"$set": {"pokemon_sort.key": key}})

    async def toggle_pokemon_sort_direction(self, trainer_id: int, default: str, other: str) -> None:
        current = {"$ifNull": ["$pokemon_sort.direction", default]}
        await self._trainers.update_one(
            {"_id": trainer_id},
            [
                {
                    "$set": {
                        "pokemon_sort.direction": {
                            "$cond": [{"$eq": [current, default]}, other, default]
                        }
                    }
                }
            ],
        )

    async def set_pokemon_display_key(self, trainer_id: int, key: str) -> None:
        await self._trainers.update_one({"_id": trainer_id}, {"$set": {"pokemon_display.key": key}})

    async def toggle_pokemon_numbers(self, trainer_id: int) -> None:
        await self._trainers.update_one(
            {"_id": trainer_id},
            [{"$set": {"pokemon_display.numbered": {"$not": [{"$ifNull": ["$pokemon_display.numbered", True]}]}}}],
        )

    async def set_pokemon_page_size(self, trainer_id: int, size: int) -> None:
        await self._trainers.update_one({"_id": trainer_id}, {"$set": {"pokemon_page_size": size}})

    async def open_reply_keyboard(self, trainer_id: int) -> bool:
        result = await self._trainers.update_one(
            {"_id": trainer_id, "reply_keyboard_open": {"$ne": True}},
            {"$set": {"reply_keyboard_open": True}},
        )
        return result.modified_count == 1

    async def close_reply_keyboard(self, trainer_id: int) -> None:
        await self._trainers.update_one({"_id": trainer_id}, {"$set": {"reply_keyboard_open": False}})

    async def spend_candy(self, trainer_id: int, reward: dict, idle_seconds: int) -> bool:
        result = await self._trainers.update_one(
            {
                "_id": trainer_id,
                "items.rare_candy": {"$gte": 1},
                **_not_in_battle_or_trade(idle_seconds),
            },
            {"$inc": {"items.rare_candy": -1}, "$push": {"pending_rewards": reward}},
        )
        return result.modified_count == 1

    async def add_move_prompt(self, trainer_id: int, prompt: dict) -> None:
        await self._trainers.update_one({"_id": trainer_id}, {"$push": {"move_prompts": prompt}})

    async def claim_move_prompt(self, trainer_id: int, prompt_id: str, idle_seconds: int) -> bool:
        result = await self._trainers.update_one(
            {"_id": trainer_id, "move_prompts.id": prompt_id, **_not_in_battle_or_trade(idle_seconds)},
            {"$pull": {"move_prompts": {"id": prompt_id}}},
        )
        return result.modified_count == 1

    async def drop_move_prompt(self, trainer_id: int, prompt_id: str) -> bool:
        result = await self._trainers.update_one(
            {"_id": trainer_id, "move_prompts.id": prompt_id},
            {"$pull": {"move_prompts": {"id": prompt_id}}},
        )
        return result.modified_count == 1

    async def claim_expired_move_prompts(self) -> tuple[int, list[dict]] | None:
        now = _now()
        trainer = await self._trainers.find_one_and_update(
            {"move_prompts.expires_at": {"$lt": now}},
            {"$pull": {"move_prompts": {"expires_at": {"$lt": now}}}},
            projection={"move_prompts": 1},
        )
        if trainer is None:
            return None
        expired = [
            prompt
            for prompt in trainer["move_prompts"]
            if prompt["expires_at"].replace(tzinfo=timezone.utc) < now
        ]
        return trainer["_id"], expired

    async def admin_increase(self, trainer_id: int, field: str, amount: int) -> None:
        await self._trainers.update_one({"_id": trainer_id}, {"$inc": {field: amount}})

    async def admin_decrease(self, trainer_id: int, field: str, amount: int) -> bool:
        result = await self._trainers.update_one(
            {"_id": trainer_id, field: {"$gte": amount}},
            {"$inc": {field: -amount}},
        )
        return result.modified_count == 1

    async def admin_set_key_stone(self, trainer_id: int, owned: bool) -> bool:
        result = await self._trainers.update_one(
            {"_id": trainer_id, "key_stone": {"$ne": owned}},
            {"$set": {"key_stone": owned}},
        )
        return result.modified_count == 1

    async def admin_add_stone(self, trainer_id: int, stone: str) -> None:
        await self._trainers.update_one({"_id": trainer_id}, {"$addToSet": {"mega_stones": stone}})

    async def admin_remove_stone(self, trainer_id: int, stone: str) -> bool:
        result = await self._trainers.update_one(
            {"_id": trainer_id, "mega_stones": stone},
            {"$pull": {"mega_stones": stone}},
        )
        return result.modified_count == 1

    async def admin_add_pokemon(
        self,
        trainer_id: int,
        document: dict,
        team_number: int | None,
    ) -> None:
        update = {
            "$inc": {"pokemon_count": 1},
            "$push": {"pending_pokemon": document},
            "$addToSet": {"caught_dex": document["dex_id"], "seen_dex": document["dex_id"]},
        }
        if team_number is not None:
            update["$push"][f"teams.{team_number}"] = str(document["_id"])
        await self._trainers.update_one({"_id": trainer_id}, update)

    async def admin_add_eggs(self, trainer_id: int, eggs: list[dict]) -> None:
        await self._trainers.update_one({"_id": trainer_id}, {"$push": {"eggs": {"$each": eggs}}})

    async def begin_ev_item(self, trainer_id: int, change: dict, idle_seconds: int) -> bool:
        field = f"items.{change['item']}"
        result = await self._trainers.update_one(
            {
                "_id": trainer_id,
                field: {"$gte": 1},
                "pending_rewards.0": {"$exists": False},
                **_not_in_battle_or_trade(idle_seconds),
            },
            {"$inc": {field: -1}, "$push": {"pending_ev_items": change}},
        )
        return result.modified_count == 1

    async def finish_ev_item(self, trainer_id: int, change_id: str) -> None:
        await self._trainers.update_one(
            {"_id": trainer_id},
            {"$pull": {"pending_ev_items": {"id": change_id}}},
        )

    async def refund_ev_item(self, trainer_id: int, change_id: str, item: str) -> None:
        await self._trainers.update_one(
            {"_id": trainer_id, "pending_ev_items.id": change_id},
            {"$pull": {"pending_ev_items": {"id": change_id}}, "$inc": {f"items.{item}": 1}},
        )

    async def begin_boost(self, trainer_id: int, boost: dict, idle_seconds: int) -> bool:
        result = await self._trainers.update_one(
            {
                "_id": trainer_id,
                "items.boost": {"$gte": 1},
                "pending_rewards.0": {"$exists": False},
                **_not_in_battle_or_trade(idle_seconds),
            },
            {"$inc": {"items.boost": -1}, "$push": {"pending_boosts": boost}},
        )
        return result.modified_count == 1

    async def finish_boost(self, trainer_id: int, boost_id: str) -> None:
        await self._trainers.update_one(
            {"_id": trainer_id},
            {"$pull": {"pending_boosts": {"id": boost_id}}},
        )

    async def refund_boost(self, trainer_id: int, boost_id: str) -> None:
        await self._trainers.update_one(
            {"_id": trainer_id, "pending_boosts.id": boost_id},
            {"$pull": {"pending_boosts": {"id": boost_id}}, "$inc": {"items.boost": 1}},
        )

    async def begin_evolution(self, trainer_id: int, evolving: dict, idle_seconds: int) -> bool:
        result = await self._trainers.update_one(
            {
                "_id": trainer_id,
                "pending_rewards.0": {"$exists": False},
                **_not_in_battle_or_trade(idle_seconds),
            },
            {"$push": {"pending_evolutions": evolving}},
        )
        return result.modified_count == 1

    async def finish_evolution(self, trainer_id: int, evolving_id: str, dex_id: int) -> None:
        await self._trainers.update_one(
            {"_id": trainer_id, "pending_evolutions.id": evolving_id},
            {"$pull": {"pending_evolutions": {"id": evolving_id}}, "$addToSet": {"caught_dex": dex_id}},
        )

    async def drop_evolution(self, trainer_id: int, evolving_id: str) -> None:
        await self._trainers.update_one(
            {"_id": trainer_id},
            {"$pull": {"pending_evolutions": {"id": evolving_id}}},
        )

    async def set_region(self, trainer_id: int, region: str, minimum_exp: int, today: str) -> bool:
        match = {"_id": trainer_id, "safari.day": {"$ne": today}, "ev_training": {"$exists": False}}
        if minimum_exp:
            match["exp_points"] = {"$gte": minimum_exp}
        result = await self._trainers.update_one(
            match,
            {"$set": {"region": region}, "$unset": {"safari": "", "balls.safari": ""}},
        )
        return result.matched_count == 1

    async def enter_safari(
        self,
        trainer_id: int,
        session: dict,
        balls: int,
        fee: int,
        idle_seconds: int,
    ) -> bool:
        result = await self._trainers.update_one(
            {
                "_id": trainer_id,
                "first_partner_id": {"$ne": None},
                "money": {"$gte": fee},
                "safari_day": {"$ne": session["day"]},
                "ev_training": {"$exists": False},
                **_not_in_battle_or_trade(idle_seconds),
            },
            {
                "$inc": {"money": -fee},
                "$set": {"safari": session, "safari_day": session["day"], "balls.safari": balls},
                "$unset": {"encounter": ""},
            },
        )
        return result.modified_count == 1

    async def leave_safari(self, trainer_id: int, idle_seconds: int | None = None) -> dict | None:
        match = {"_id": trainer_id, "safari": {"$exists": True}}
        if idle_seconds is not None:
            match.update(_not_in_battle_or_trade(idle_seconds))
        trainer = await self._trainers.find_one_and_update(
            match,
            {"$unset": {"safari": "", "balls.safari": "", "encounter": ""}},
            projection={"safari": 1},
        )
        return trainer["safari"] if trainer else None

    async def start_safari_encounter(
        self,
        trainer_id: int,
        encounter: dict,
        today: str,
        hunt_limit: int,
        idle_seconds: int,
    ) -> dict | None:
        return await self._trainers.find_one_and_update(
            {
                "_id": trainer_id,
                "safari.day": today,
                "safari.hunts": {"$lt": hunt_limit},
                "balls.safari": {"$gte": 1},
                **_not_in_battle_or_trade(idle_seconds),
            },
            {
                "$set": {"encounter": {**encounter, "updated_at": _now()}},
                "$inc": {"safari.hunts": 1},
                "$addToSet": {"seen_dex": encounter["wild"]["dex_id"]},
            },
            projection={"safari": 1, "balls": 1},
            return_document=ReturnDocument.AFTER,
        )

    async def enter_ev_training(self, trainer_id: int, session: dict, fee: int, idle_seconds: int) -> bool:
        result = await self._trainers.update_one(
            {
                "_id": trainer_id,
                "first_partner_id": {"$ne": None},
                "money": {"$gte": fee},
                "safari": {"$exists": False},
                "ev_training": {"$exists": False},
                **_not_in_battle_or_trade(idle_seconds),
            },
            {
                "$inc": {"money": -fee},
                "$set": {"ev_training": session},
                "$unset": {"encounter": ""},
            },
        )
        return result.modified_count == 1

    async def leave_ev_training(self, trainer_id: int, idle_seconds: int | None = None) -> dict | None:
        match = {"_id": trainer_id, "ev_training": {"$exists": True}}
        if idle_seconds is not None:
            match.update(_not_in_battle_or_trade(idle_seconds))
        trainer = await self._trainers.find_one_and_update(
            match,
            {"$unset": {"ev_training": "", "encounter": ""}},
            projection={"ev_training": 1},
        )
        return trainer["ev_training"] if trainer else None

    async def start_ev_training_encounter(
        self,
        trainer_id: int,
        encounter: dict,
        hunt_limit: int,
        idle_seconds: int,
    ) -> dict | None:
        return await self._trainers.find_one_and_update(
            {
                "_id": trainer_id,
                "ev_training.hunts": {"$lt": hunt_limit},
                **_not_in_battle_or_trade(idle_seconds),
            },
            {
                "$set": {"encounter": {**encounter, "updated_at": _now()}},
                "$inc": {"ev_training.hunts": 1},
                "$addToSet": {"seen_dex": encounter["wild"]["dex_id"]},
            },
            projection={"ev_training": 1},
            return_document=ReturnDocument.AFTER,
        )

    async def _paying(self, trainer_id: int, amount: int, write) -> int | None:
        if amount <= 0:
            return 0 if await write(0, {}, {}) else None
        day = _now().date().isoformat()
        for _ in range(EARNING_ATTEMPTS):
            trainer = await self._trainers.find_one({"_id": trainer_id}, projection={"daily_earned": 1})
            if trainer is None:
                return None
            current = trainer.get("daily_earned")
            paid = earnings.payable(current, amount, day)
            fields = {"daily_earned": earnings.recorded(current, paid, day)} if paid else {}
            if await write(paid, {"daily_earned": current}, fields):
                return paid
        return None

    async def earn_money(self, trainer_id: int, amount: int) -> int | None:
        async def write(paid: int, guard: dict, fields: dict) -> bool:
            if not paid:
                return True
            result = await self._trainers.update_one(
                {"_id": trainer_id, **guard},
                {"$inc": {"money": paid}, "$set": fields},
            )
            return result.modified_count == 1

        return await self._paying(trainer_id, amount, write)

    async def set_card_choice(self, trainer_id: int, field: str, value: int | str) -> None:
        await self._trainers.update_one({"_id": trainer_id}, {"$set": {f"card.{field}": value}})

    async def begin_gift(self, trainer_id: int, gift: dict) -> bool:
        result = await self._trainers.update_one(
            {"_id": trainer_id, "money": {"$gte": gift["amount"]}},
            {"$inc": {"money": -gift["amount"]}, "$push": {"pending_gifts": gift}},
        )
        return result.modified_count == 1

    async def receive_gift(self, gift: dict) -> None:
        await self._trainers.update_one(
            {"_id": gift["to"], "applied_gifts": {"$ne": gift["id"]}},
            {
                "$inc": {"money": gift["amount"]},
                "$push": {"applied_gifts": {"$each": [gift["id"]], "$slice": -APPLIED_GIFTS_KEPT}},
            },
        )

    async def finish_gift(self, trainer_id: int, gift_id: str) -> None:
        await self._trainers.update_one(
            {"_id": trainer_id},
            {"$pull": {"pending_gifts": {"id": gift_id}}},
        )

    async def buy_goods(self, trainer_id: int, field: str, amount: int, cost: int) -> bool:
        result = await self._trainers.update_one(
            {"_id": trainer_id, "money": {"$gte": cost}},
            {"$inc": {"money": -cost, field: amount}},
        )
        return result.modified_count == 1

    async def sell_goods(self, trainer_id: int, field: str, amount: int, gain: int) -> bool:
        result = await self._trainers.update_one(
            {"_id": trainer_id, field: {"$gte": amount}},
            {"$inc": {"money": gain, field: -amount}},
        )
        return result.modified_count == 1

    async def sell_stone(self, trainer_id: int, stone: str, price: int, idle_seconds: int) -> bool:
        result = await self._trainers.update_one(
            {"_id": trainer_id, "mega_stones": stone, **_not_in_battle_or_trade(idle_seconds)},
            {"$pull": {"mega_stones": stone}, "$inc": {"money": price}},
        )
        return result.modified_count == 1

    async def buy_key_stone(self, trainer_id: int, cost: int) -> bool:
        result = await self._trainers.update_one(
            {"_id": trainer_id, "money": {"$gte": cost}, "key_stone": {"$ne": True}},
            {"$inc": {"money": -cost}, "$set": {"key_stone": True}},
        )
        return result.modified_count == 1

    async def has_key_stone(self, trainer_id: int) -> bool:
        return await self._trainers.count_documents({"_id": trainer_id, "key_stone": True}, limit=1) == 1

    async def buy_tm(self, trainer_id: int, tm: str, price: int, purchase: str, purchases_kept: int) -> bool:
        result = await self._trainers.update_one(
            {"_id": trainer_id, "money": {"$gte": price}, "bought_store_tms": {"$ne": purchase}},
            {
                "$inc": {"money": -price, f"tms.{tm}": 1},
                "$push": {"bought_store_tms": {"$each": [purchase], "$slice": -purchases_kept}},
            },
        )
        return result.modified_count == 1

    async def sell_tm(self, trainer_id: int, tm: str, price: int) -> bool:
        result = await self._trainers.update_one(
            {"_id": trainer_id, f"tms.{tm}": {"$gt": 0}},
            {"$inc": {"money": price, f"tms.{tm}": -1}},
        )
        return result.modified_count == 1

    async def begin_teaching(self, trainer_id: int, teaching: dict, idle_seconds: int) -> bool:
        result = await self._trainers.update_one(
            {
                "_id": trainer_id,
                f"tms.{teaching['tm']}": {"$gt": 0},
                "pending_rewards.0": {"$exists": False},
                **_not_in_battle_or_trade(idle_seconds),
            },
            {"$inc": {f"tms.{teaching['tm']}": -1}, "$push": {"pending_teachings": teaching}},
        )
        return result.modified_count == 1

    async def finish_teaching(self, trainer_id: int, teaching_id: str) -> None:
        await self._trainers.update_one(
            {"_id": trainer_id},
            {"$pull": {"pending_teachings": {"id": teaching_id}}},
        )

    async def refund_teaching(self, trainer_id: int, teaching_id: str, tm: str) -> None:
        await self._trainers.update_one(
            {"_id": trainer_id, "pending_teachings.id": teaching_id},
            {"$pull": {"pending_teachings": {"id": teaching_id}}, "$inc": {f"tms.{tm}": 1}},
        )

    async def in_battle(self, trainer_id: int, idle_seconds: int) -> bool:
        match = {
            "_id": trainer_id,
            "$or": [
                {"challenge_id": {"$exists": True}},
                {
                    "encounter.state": "battling",
                    "encounter.updated_at": {"$gte": _now() - timedelta(seconds=idle_seconds)},
                },
            ],
        }
        return await self._trainers.count_documents(match, limit=1) == 1

    async def in_trade(self, trainer_id: int) -> bool:
        return await self._trainers.count_documents({"_id": trainer_id, "trade_id": {"$exists": True}}, limit=1) == 1

    def _can_trade(self, trainer_id: int, idle_seconds: int) -> dict:
        return {
            "_id": trainer_id,
            "first_partner_id": {"$ne": None},
            "pending_releases.0": {"$exists": False},
            **_not_in_battle_or_trade(idle_seconds),
        }

    async def can_trade(self, trainer_id: int, idle_seconds: int) -> bool:
        return await self._trainers.count_documents(self._can_trade(trainer_id, idle_seconds), limit=1) == 1

    async def join_trade(self, trainer_id: int, trade_id: str, idle_seconds: int) -> dict | None:
        return await self._trainers.find_one_and_update(
            self._can_trade(trainer_id, idle_seconds),
            {
                "$set": {"trade_id": trade_id},
                "$unset": {"encounter": "", "nickname_prompt": ""},
            },
            projection={"encounter": 1},
        )

    async def leave_trade(self, trainer_id: int, trade_id: str) -> None:
        await self._trainers.update_one({"_id": trainer_id, "trade_id": trade_id}, {"$unset": {"trade_id": ""}})

    async def save_challenge_settings(self, trainer_id: int, settings: dict) -> None:
        await self._trainers.update_one({"_id": trainer_id}, {"$set": {"challenge_settings": settings}})

    async def join_challenge(self, trainer_id: int, challenge_id: str, idle_seconds: int) -> dict | None:
        return await self._trainers.find_one_and_update(
            self._can_trade(trainer_id, idle_seconds),
            {
                "$set": {"challenge_id": challenge_id},
                "$unset": {"encounter": "", "nickname_prompt": ""},
            },
            projection={"encounter": 1},
        )

    async def finish_challenge(self, trainer_id: int, challenge_id: str, payout: Payout) -> int | None:
        earned = {
            "wins": payout.wins,
            "losses": payout.losses,
            "exp_points": _earned_exp(payout.rewards),
        }
        fields = {
            field: {"$add": [{"$ifNull": [f"${field}", 0]}, amount]}
            for field, amount in earned.items()
            if amount
        }
        if payout.rewards:
            fields["pending_rewards"] = {
                "$concatArrays": [{"$ifNull": ["$pending_rewards", []]}, {"$literal": payout.rewards}]
            }

        async def write(paid: int, guard: dict, earned_fields: dict) -> bool:
            changes = {**fields, **{field: {"$literal": value} for field, value in earned_fields.items()}}
            money = paid if payout.money > 0 else payout.money
            if money:
                changes["money"] = {"$max": [0, {"$add": [{"$ifNull": ["$money", 0]}, money]}]}
            stages = [{"$set": changes}] if changes else []
            result = await self._trainers.update_one(
                {"_id": trainer_id, "challenge_id": challenge_id, **guard},
                [*stages, {"$unset": "challenge_id"}],
            )
            return result.modified_count == 1

        return await self._paying(trainer_id, max(payout.money, 0), write)

    async def hand_over(
        self,
        trainer_id: int,
        trade_id: str,
        pokemon_id: str,
        incoming_dex_id: int,
        team_numbers: list[int],
    ) -> None:
        await self._trainers.update_one(
            {"_id": trainer_id, "trade_id": trade_id},
            {
                "$pull": {f"teams.{number}": pokemon_id for number in team_numbers},
                "$addToSet": {"caught_dex": incoming_dex_id},
            },
        )

    async def receive_traded(self, trainer_id: int, trade_id: str, pokemon_id: str, team_size: int) -> None:
        trainer = await self._trainers.find_one(
            {"_id": trainer_id, "trade_id": trade_id},
            projection={"active_team": 1},
        )
        if trainer is None:
            return
        team = f"teams.{trainer['active_team']}"
        await self._trainers.update_one(
            {
                "_id": trainer_id,
                "trade_id": trade_id,
                f"{team}.{team_size - 1}": {"$exists": False},
                team: {"$ne": pokemon_id},
            },
            {"$push": {team: pokemon_id}, "$unset": {"trade_id": ""}},
        )
        await self.leave_trade(trainer_id, trade_id)

    async def select_team(self, trainer_id: int, number: int, idle_seconds: int) -> bool:
        result = await self._trainers.update_one(
            {"_id": trainer_id, **_not_in_battle_or_trade(idle_seconds)},
            {"$set": {"active_team": number}},
        )
        return result.matched_count == 1

    async def add_team_member(
        self,
        trainer_id: int,
        number: int,
        pokemon_id: str,
        team_size: int,
        idle_seconds: int,
    ) -> bool:
        team = f"teams.{number}"
        result = await self._trainers.update_one(
            {
                "_id": trainer_id,
                team: {"$ne": pokemon_id},
                f"{team}.{team_size - 1}": {"$exists": False},
                **_not_in_battle_or_trade(idle_seconds),
            },
            {"$push": {team: pokemon_id}},
        )
        return result.modified_count == 1

    async def remove_team_member(self, trainer_id: int, number: int, pokemon_id: str, idle_seconds: int) -> bool:
        team = f"teams.{number}"
        result = await self._trainers.update_one(
            {"_id": trainer_id, team: pokemon_id, **_not_in_battle_or_trade(idle_seconds)},
            {"$pull": {team: pokemon_id}},
        )
        return result.modified_count == 1

    async def replace_team(
        self,
        trainer_id: int,
        number: int,
        expected: list[str],
        members: list[str],
        idle_seconds: int,
    ) -> bool:
        team = f"teams.{number}"
        result = await self._trainers.update_one(
            {"_id": trainer_id, team: expected, **_not_in_battle_or_trade(idle_seconds)},
            {"$set": {team: members}},
        )
        return result.modified_count == 1

    async def save_team_as(
        self,
        trainer_id: int,
        number: int,
        expected: list[str],
        target: int,
        idle_seconds: int,
    ) -> bool:
        result = await self._trainers.update_one(
            {"_id": trainer_id, "active_team": number, f"teams.{number}": expected, **_not_in_battle_or_trade(idle_seconds)},
            {"$set": {f"teams.{target}": expected, "active_team": target}},
        )
        return result.matched_count == 1

    async def clear_pending(self, trainer_id: int, pokemon_id: ObjectId) -> None:
        await self._trainers.update_one(
            {"_id": trainer_id},
            {"$pull": {"pending_pokemon": {"_id": pokemon_id}}},
        )

    async def clear_pending_reward(self, trainer_id: int, reward_id: str) -> None:
        await self._trainers.update_one(
            {"_id": trainer_id},
            {"$pull": {"pending_rewards": {"id": reward_id}}},
        )

    async def set_release_prompt(self, trainer_id: int, pokemon_id: str, message_id: int, previous_body: str) -> None:
        await self._trainers.update_one(
            {"_id": trainer_id},
            {
                "$set": {
                    "release_prompt": {
                        "pokemon_id": pokemon_id,
                        "message_id": message_id,
                        "previous_body": previous_body,
                    }
                }
            },
        )

    async def take_release_prompt(self, trainer_id: int, pokemon_id: str, message_id: int) -> str | None:
        trainer = await self._trainers.find_one_and_update(
            {
                "_id": trainer_id,
                "release_prompt.pokemon_id": pokemon_id,
                "release_prompt.message_id": message_id,
            },
            {"$unset": {"release_prompt": ""}},
            projection={"release_prompt": 1},
        )
        return trainer["release_prompt"]["previous_body"] if trainer else None

    async def has_spare_pokemon(self, trainer_id: int) -> bool:
        match = {"_id": trainer_id, "$expr": {"$gt": [_pokemon_left(), 1]}}
        return await self._trainers.count_documents(match, limit=1) == 1

    async def begin_release(
        self,
        trainer_id: int,
        pokemon_id: str,
        team_numbers: list[int],
        idle_seconds: int,
    ) -> bool:
        result = await self._trainers.update_one(
            {
                "_id": trainer_id,
                "$expr": {"$gt": [_pokemon_left(), 1]},
                "pending_releases": {"$ne": pokemon_id},
                **_not_in_battle_or_trade(idle_seconds),
            },
            {
                "$pull": {f"teams.{number}": pokemon_id for number in team_numbers},
                "$push": {"pending_releases": pokemon_id},
            },
        )
        return result.modified_count == 1

    async def finish_release(self, trainer_id: int, pokemon_id: str, counted: bool) -> None:
        update = {"$pull": {"pending_releases": pokemon_id}}
        if counted:
            update["$inc"] = {"pokemon_count": -1}
        await self._trainers.update_one({"_id": trainer_id, "pending_releases": pokemon_id}, update)

    async def set_nickname_prompt(self, trainer_id: int, pokemon_id: str, chat_id: int, message_id: int) -> None:
        await self._trainers.update_one(
            {"_id": trainer_id, "trade_id": {"$exists": False}},
            {
                "$set": {
                    "nickname_prompt": {
                        "chat_id": chat_id,
                        "message_id": message_id,
                        "pokemon_id": pokemon_id,
                    }
                }
            },
        )

    async def clear_nickname_prompt(self, trainer_id: int, chat_id: int, message_id: int) -> None:
        await self._trainers.update_one(
            {
                "_id": trainer_id,
                "nickname_prompt.chat_id": chat_id,
                "nickname_prompt.message_id": message_id,
            },
            {"$unset": {"nickname_prompt": ""}},
        )

    async def start_encounter(self, trainer_id: int, encounter: dict, idle_seconds: int) -> bool:
        now = _now()
        result = await self._trainers.update_one(
            {
                "_id": trainer_id,
                "first_partner_id": {"$ne": None},
                **_not_in_battle_or_trade(idle_seconds),
            },
            {
                "$set": {"encounter": {**encounter, "updated_at": now}},
                "$addToSet": {"seen_dex": encounter["wild"]["dex_id"]},
            },
        )
        return result.matched_count == 1

    async def start_expert_encounter(self, trainer_id: int, encounter: dict, idle_seconds: int) -> bool:
        result = await self._trainers.update_one(
            {
                "_id": trainer_id,
                "first_partner_id": {"$ne": None},
                **_not_in_battle_or_trade(idle_seconds),
            },
            {"$set": {"encounter": {**encounter, "updated_at": _now()}}},
        )
        return result.matched_count == 1

    async def begin_expert_battle(
        self,
        trainer_id: int,
        encounter_id: str,
        team_number: int,
        team_ids: list[str],
        fields: dict,
        seen: list[int],
    ) -> dict | None:
        changes = {f"encounter.{name}": value for name, value in fields.items()}
        return await self._trainers.find_one_and_update(
            {
                "_id": trainer_id,
                "encounter.id": encounter_id,
                "encounter.state": "found",
                "active_team": team_number,
                f"teams.{team_number}": team_ids,
            },
            {
                "$set": {**changes, "encounter.state": "battling", "encounter.updated_at": _now()},
                "$addToSet": {"seen_dex": {"$each": seen}},
            },
            return_document=ReturnDocument.AFTER,
        )

    async def send_out_expert_pokemon(
        self,
        trainer_id: int,
        encounter_id: str,
        turn: int,
        player_hp: int,
        player_id: str,
        rival: dict,
        rival_hp: int,
        expert_team: list[dict],
        rewards: list[dict],
    ) -> bool:
        trainer = await self._trainers.find_one_and_update(
            {
                "_id": trainer_id,
                "encounter.id": encounter_id,
                "encounter.state": "battling",
                "encounter.turn": turn,
            },
            {
                "$set": {
                    "encounter.player_hp": player_hp,
                    "encounter.wild": rival,
                    "encounter.wild_hp": rival_hp,
                    "encounter.expert_team": expert_team,
                    "encounter.participants": [player_id],
                    "encounter.turn": turn + 1,
                    "encounter.updated_at": _now(),
                },
                "$push": {"pending_rewards": {"$each": rewards}},
                "$inc": {"exp_points": _earned_exp(rewards)},
            },
            projection={"_id": 1},
        )
        return trainer is not None

    async def grant_found_tm(self, trainer_id: int, tm: str, idle_seconds: int) -> bool:
        result = await self._trainers.update_one(
            {"_id": trainer_id, **_not_in_battle_or_trade(idle_seconds)},
            {"$inc": {f"tms.{tm}": 1}},
        )
        return result.matched_count == 1

    async def grant_found_stone(self, trainer_id: int, stone: str, idle_seconds: int) -> bool:
        result = await self._trainers.update_one(
            {"_id": trainer_id, **_not_in_battle_or_trade(idle_seconds)},
            {"$addToSet": {"mega_stones": stone}},
        )
        return result.matched_count == 1

    async def grant_found_egg(self, trainer_id: int, egg: dict, idle_seconds: int) -> bool:
        result = await self._trainers.update_one(
            {"_id": trainer_id, **_not_in_battle_or_trade(idle_seconds)},
            {"$push": {"eggs": egg}},
        )
        return result.matched_count == 1

    async def claim_mom_gift(self, trainer_id: int, increases: dict) -> bool:
        result = await self._trainers.update_one(
            {"_id": trainer_id, "mom_gift": {"$exists": False}, "seen_dex.0": {"$exists": False}},
            {"$set": {"mom_gift": True}, "$inc": increases},
        )
        return result.modified_count == 1

    async def next_due_egg(self) -> dict | None:
        return await self._trainers.find_one({"eggs.hatch_at": {"$lte": _now()}}, {"eggs": 1})

    async def hatch_egg(self, trainer_id: int, egg_id: str, document: dict) -> bool:
        result = await self._trainers.update_one(
            {"_id": trainer_id, "eggs.id": egg_id},
            {
                "$pull": {"eggs": {"id": egg_id}},
                "$inc": {"pokemon_count": 1},
                "$push": {"pending_pokemon": document},
                "$addToSet": {"caught_dex": document["dex_id"], "seen_dex": document["dex_id"]},
            },
        )
        return result.modified_count == 1

    async def begin_battle(self, trainer_id: int, encounter_id: str) -> dict | None:
        return await self._trainers.find_one_and_update(
            {"_id": trainer_id, "encounter.id": encounter_id, "encounter.state": "found"},
            {"$set": {"encounter.state": "battling", "encounter.updated_at": _now()}},
            return_document=ReturnDocument.AFTER,
        )

    async def apply_turn(
        self,
        trainer_id: int,
        encounter_id: str,
        turn: int,
        player_hp: int,
        wild_hp: int,
        battle_over: bool,
        reward: int = 0,
        rewards: list[dict] | None = None,
    ) -> int | None:
        if battle_over:
            update = {"$unset": {"encounter": ""}}
            if rewards:
                update["$push"] = {"pending_rewards": {"$each": rewards}}
                update.setdefault("$inc", {})["exp_points"] = _earned_exp(rewards)
        else:
            update = {
                "$set": {
                    "encounter.player_hp": player_hp,
                    "encounter.wild_hp": wild_hp,
                    "encounter.turn": turn + 1,
                    "encounter.updated_at": _now(),
                }
            }

        async def write(paid: int, guard: dict, fields: dict) -> bool:
            trainer = await self._trainers.find_one_and_update(
                {
                    "_id": trainer_id,
                    "encounter.id": encounter_id,
                    "encounter.state": "battling",
                    "encounter.turn": turn,
                    **guard,
                },
                _with_money(update, paid, fields),
                projection={"_id": 1},
            )
            return trainer is not None

        return await self._paying(trainer_id, reward if battle_over else 0, write)

    async def set_encounter_message(self, trainer_id: int, encounter_id: str, chat_id: int, message_id: int) -> None:
        await self._trainers.update_one(
            {"_id": trainer_id, "encounter.id": encounter_id},
            {"$set": {"encounter.message": {"chat_id": chat_id, "message_id": message_id}}},
        )

    async def touch_encounter(self, trainer_id: int, encounter_id: str) -> None:
        await self._trainers.update_one(
            {"_id": trainer_id, "encounter.id": encounter_id},
            {"$set": {"encounter.updated_at": _now()}},
        )

    async def claim_idle_encounter(self, idle_seconds: int) -> dict | None:
        trainer = await self._trainers.find_one_and_update(
            {"encounter.updated_at": {"$lt": _now() - timedelta(seconds=idle_seconds)}},
            [
                {
                    "$set": {
                        "last_fled": {
                            "id": "$encounter.id",
                            "wild": "$encounter.wild",
                            "expert": "$encounter.expert",
                        }
                    }
                },
                {"$unset": "encounter"},
            ],
            projection={"encounter": 1},
        )
        return trainer["encounter"] if trainer else None

    async def end_battle(self, trainer_id: int, encounter_id: str) -> bool:
        trainer = await self._trainers.find_one_and_update(
            {"_id": trainer_id, "encounter.id": encounter_id, "encounter.state": "battling"},
            {"$unset": {"encounter": ""}},
            projection={"_id": 1},
        )
        return trainer is not None

    async def change_battle_form(self, trainer_id: int, encounter_id: str, pokemon_id: str, form_id: int) -> bool:
        result = await self._trainers.update_one(
            {
                "_id": trainer_id,
                "encounter.id": encounter_id,
                "encounter.state": "battling",
                "encounter.player_id": pokemon_id,
                "encounter.forms": {"$exists": False},
            },
            {
                "$set": {
                    "encounter.forms": {pokemon_id: form_id},
                    "encounter.player.form_id": form_id,
                    "encounter.updated_at": _now(),
                }
            },
        )
        return result.modified_count == 1

    async def switch_pokemon(
        self,
        trainer_id: int,
        encounter_id: str,
        turn: int,
        outgoing_id: str,
        outgoing_hp: int,
        incoming_id: str,
        incoming: dict,
        incoming_hp: int,
        battle_over: bool,
        rewards: list[dict] | None = None,
    ) -> bool:
        if battle_over:
            update = {"$unset": {"encounter": ""}}
            if rewards:
                update["$push"] = {"pending_rewards": {"$each": rewards}}
                update["$inc"] = {"exp_points": _earned_exp(rewards)}
        else:
            update = {
                "$set": {
                    "encounter.player": incoming,
                    "encounter.player_id": incoming_id,
                    "encounter.player_hp": incoming_hp,
                    f"encounter.team_hp.{outgoing_id}": outgoing_hp,
                    "encounter.turn": turn + 1,
                    "encounter.updated_at": _now(),
                },
                "$addToSet": {"encounter.participants": incoming_id},
            }
        trainer = await self._trainers.find_one_and_update(
            {
                "_id": trainer_id,
                "encounter.id": encounter_id,
                "encounter.state": "battling",
                "encounter.turn": turn,
            },
            update,
            projection={"_id": 1},
        )
        return trainer is not None

    async def throw_ball(
        self,
        trainer_id: int,
        encounter_id: str,
        turn: int,
        ball: str,
        caught_document: dict | None,
        player_hp: int,
        battle_over: bool,
        team_number: int | None = None,
        team_size: int = 0,
        rewards: list[dict] | None = None,
        event_day: str | None = None,
        event_reward: int = 0,
        held_stone: str | None = None,
        drop_field: str | None = None,
        drop_amount: int = 0,
        leave_safari: bool = False,
    ) -> int | None:
        update = {"$inc": {f"balls.{ball}": -1, "balls_used": 1}}
        match = {
            "_id": trainer_id,
            "encounter.id": encounter_id,
            "encounter.state": "battling",
            "encounter.turn": turn,
            f"balls.{ball}": {"$gte": 1},
        }
        if caught_document is not None:
            update["$inc"]["pokemon_count"] = 1
            update["$inc"]["total_caught"] = 1
            update["$push"] = {"pending_pokemon": caught_document}
            if team_number is not None:
                update["$push"][f"teams.{team_number}"] = str(caught_document["_id"])
                match["active_team"] = team_number
                match[f"teams.{team_number}.{team_size - 1}"] = {"$exists": False}
            update["$addToSet"] = {"caught_dex": caught_document["dex_id"]}
            if held_stone is not None:
                update["$addToSet"]["mega_stones"] = held_stone
        if rewards:
            update.setdefault("$push", {})["pending_rewards"] = {"$each": rewards}
            update["$inc"]["exp_points"] = _earned_exp(rewards)
        if battle_over:
            update["$unset"] = {"encounter": ""}
        else:
            update["$set"] = {
                "encounter.player_hp": player_hp,
                "encounter.turn": turn + 1,
                "encounter.updated_at": _now(),
            }
        if event_day is not None:
            match["event_reward_day"] = {"$ne": event_day}
            update.setdefault("$set", {})["event_reward_day"] = event_day
        if drop_field is not None and drop_field != "money":
            update["$inc"][drop_field] = update["$inc"].get(drop_field, 0) + drop_amount
        if leave_safari:
            del update["$inc"][f"balls.{ball}"]
            update["$unset"].update({"safari": "", f"balls.{ball}": ""})

        async def write(paid: int, guard: dict, fields: dict) -> bool:
            trainer = await self._trainers.find_one_and_update(
                {**match, **guard},
                _with_money(update, paid, fields),
                projection={"_id": 1},
            )
            return trainer is not None

        money = event_reward + (drop_amount if drop_field == "money" else 0)
        return await self._paying(trainer_id, money, write)
