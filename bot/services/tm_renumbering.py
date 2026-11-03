import logging

from bot.game import tms as rules
from bot.services.settling import settle_pending
from bot.storage.stores import Stores

MIGRATION_NAME = "tm_renumbering"

logger = logging.getLogger(__name__)


async def run(stores: Stores) -> None:
    if await stores.trainers.migration_done(MIGRATION_NAME):
        return
    failed = 0
    async for trainer_id in stores.trainers.tm_owners_to_renumber():
        await settle_pending(stores, trainer_id)
        trainer = await stores.trainers.get(trainer_id)
        renumbered = rules.renumbered_owned(trainer["tms"])
        if not await stores.trainers.renumber_tms(trainer_id, trainer["tms"], renumbered):
            failed += 1
            logger.error("Could not renumber the TMs of trainer %s", trainer_id)
    if failed:
        raise RuntimeError(f"Could not renumber the TMs of {failed} trainers")
    await stores.trainers.finish_migration(MIGRATION_NAME)
