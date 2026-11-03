IDLE_SECONDS = 120
RETRY_SECONDS = 30
FINISHED_KEPT_SECONDS = 30 * 24 * 60 * 60

REQUESTED = "requested"
JOINING = "joining"
CHOOSING_REQUESTER = "choosing_requester"
CHOOSING_PARTNER = "choosing_partner"
CONFIRMING = "confirming"
SWAPPING = "swapping"
CLOSING = "closing"
DONE = "done"
CLOSED = "closed"

ACTIVE_STATES = (REQUESTED, JOINING, CHOOSING_REQUESTER, CHOOSING_PARTNER, CONFIRMING)
UNFINISHED_STATES = (SWAPPING, CLOSING)

CANCELLED = "cancelled"
EXPIRED = "expired"

REQUESTER = "requester"
PARTNER = "partner"
SIDES = (REQUESTER, PARTNER)
CHOOSER_SIDE = {CHOOSING_REQUESTER: REQUESTER, CHOOSING_PARTNER: PARTNER}
STATE_AFTER_CHOICE = {CHOOSING_REQUESTER: CHOOSING_PARTNER, CHOOSING_PARTNER: CONFIRMING}


def side_of(name: str, trainer_id: int) -> dict:
    return {"id": trainer_id, "name": name, "offer": None}


def offer_of(pokemon: dict) -> dict:
    return {
        "pokemon_id": str(pokemon["_id"]),
        "dex_id": pokemon["dex_id"],
    }


def chooser_id(trade: dict) -> int | None:
    side = CHOOSER_SIDE.get(trade["state"])
    return trade[side]["id"] if side else None


def is_participant(trade: dict, trainer_id: int) -> bool:
    return any(trade[side]["id"] == trainer_id for side in SIDES)
