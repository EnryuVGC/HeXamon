from dataclasses import dataclass

from bot.game import referrals as rules
from bot.storage.stores import Stores


@dataclass(frozen=True)
class Payout:
    referrer_id: int
    name: str
    count: int
    milestone: rules.Milestone
    bonus: int = 0


async def referral_count(stores: Stores, trainer_id: int) -> int:
    trainer = await stores.trainers.get(trainer_id)
    return trainer.get("referral_count", 0) if trainer else 0


async def use_link(stores: Stores, trainer_id: int, name: str, payload: str | None) -> int | None:
    referrer_id = rules.referrer_of_payload(payload)
    if referrer_id is None or referrer_id == trainer_id:
        return None
    if not await stores.trainers.has_started(referrer_id):
        return None
    if not await stores.trainers.set_referrer(trainer_id, referrer_id, name):
        return None
    return referrer_id


async def next_payout(stores: Stores) -> Payout | None:
    while (invited := await stores.trainers.next_unpaid_referral(rules.TARGET_EXP)) is not None:
        referral = invited["referred_by"]
        referrer = await stores.trainers.get(referral["id"])
        if referrer is None or invited["_id"] in referrer.get("applied_referrals", []):
            await stores.trainers.clear_referrer(invited["_id"])
            continue
        count = referrer.get("referral_count", 0)
        milestone = rules.roll_milestone(count + 1, referrer.get("mega_stones", []))
        paid = await stores.trainers.pay_referral(
            referral["id"],
            invited["_id"],
            count,
            rules.reward_counters(milestone),
            milestone.stone,
        )
        if paid is None:
            return None
        await stores.trainers.clear_referrer(invited["_id"])
        return Payout(referral["id"], referral["name"], count + 1, milestone, paid)
    return None
