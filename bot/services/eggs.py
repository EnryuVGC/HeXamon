from dataclasses import dataclass

from bot.game import creatures, eggs as rules
from bot.storage.pokemon import as_document, new_id
from bot.storage.stores import Stores


@dataclass
class Hatched:
    trainer_id: int
    pokemon: dict


async def hatch_next(stores: Stores) -> Hatched | None:
    trainer = await stores.trainers.next_due_egg()
    if trainer is None:
        return None
    trainer_id = trainer["_id"]
    egg = min(trainer["eggs"], key=lambda entry: entry["hatch_at"])
    document = as_document(trainer_id, new_id(), creatures.with_sort_fields(rules.hatch()))
    if not await stores.trainers.hatch_egg(trainer_id, egg["id"], document):
        return None
    await stores.pokemon.insert_if_missing(document)
    await stores.trainers.clear_pending(trainer_id, document["_id"])
    return Hatched(trainer_id, document)
