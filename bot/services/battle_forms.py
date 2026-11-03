from bot.game import challenges as rules
from bot.game import creatures
from bot.storage.stores import Stores


async def live_forms(stores: Stores, trainer: dict) -> dict[str, int]:
    forms = dict(trainer.get("encounter", {}).get("forms", {}))
    challenge_id = trainer.get("challenge_id")
    if challenge_id is None:
        return forms
    challenge = await stores.challenges.get(challenge_id)
    if challenge is None or challenge["state"] != rules.BATTLING:
        return forms
    side = rules.side_named(challenge, trainer["_id"])
    if side is None:
        return forms
    forms.update(rules.team_forms(challenge[side]))
    return forms


def apply_forms(pokemon: list[dict], forms: dict[str, int]) -> list[dict]:
    return [
        creatures.with_form(member, forms[str(member["_id"])]) if str(member["_id"]) in forms else member
        for member in pokemon
    ]


async def overlay(stores: Stores, trainer_id: int, pokemon: list[dict], trainer: dict | None = None) -> list[dict]:
    trainer = trainer or await stores.trainers.get(trainer_id)
    if not trainer or not pokemon:
        return pokemon
    return apply_forms(pokemon, await live_forms(stores, trainer))
