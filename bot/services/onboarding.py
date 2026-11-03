from bot.game import creatures
from bot.game.teams import empty_teams
from bot.game.catching import STARTING_BALLS
from bot.game.starters import (
    STARTING_LEVEL,
    STARTING_MONEY,
    STARTING_REGION,
    Partner,
    find_first_partner,
    first_partners,
    no_choice_partner,
)
from bot.services.settling import settle_pending
from bot.storage.pokemon import as_document, new_id
from bot.storage.stores import Stores


async def has_started(stores: Stores, trainer_id: int) -> bool:
    return await stores.trainers.has_started(trainer_id)


async def needs_first_partner(stores: Stores, trainer_id: int) -> bool:
    trainer = await stores.trainers.register(trainer_id, STARTING_REGION, STARTING_BALLS)
    return trainer["first_partner_id"] is None


def available_partners() -> list[Partner]:
    return first_partners()


def fallback_partner() -> Partner:
    return no_choice_partner()


async def choose_first_partner(
    stores: Stores,
    trainer_id: int,
    dex_id: int,
) -> tuple[Partner, str] | None:
    partner = find_first_partner(dex_id)
    if partner is None:
        return None
    pokemon_id = new_id()
    document = as_document(
        trainer_id,
        pokemon_id,
        creatures.with_sort_fields(creatures.new_pokemon(partner.dex_id, STARTING_LEVEL)),
    )
    teams = {**empty_teams(), "1": [pokemon_id]}
    claimed = await stores.trainers.claim_first_partner(
        trainer_id, document, STARTING_REGION, STARTING_BALLS, teams, STARTING_MONEY
    )
    if not claimed:
        return None
    await settle_pending(stores, trainer_id)
    return partner, pokemon_id
