from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from bot.game import creatures, experience, pokedex, tms as teaching_rules
from bot.game.encounters import BATTLE_IDLE_SECONDS
from bot.services import evolving
from bot.services.settling import settle_pending
from bot.storage.pokemon import new_id
from bot.storage.stores import Stores

GAVE = "gave"
NO_CANDY = "no_candy"
MAX_LEVEL = "max_level"
IN_BATTLE = "in_battle"
IN_TRADE = "in_trade"
GONE = "gone"
FAILED = "failed"
LEARNED = "learned"
NEEDS_FORGET = "needs_forget"
EXPIRED = "expired"

PROMPT_SECONDS = 600


@dataclass
class CandyResult:
    status: str
    pokemon: dict | None = None
    old_level: int = 0
    new_level: int = 0
    learned: list[str] | None = None
    waiting: list[str] | None = None
    ready: bool = False


@dataclass
class PromptView:
    prompt: dict
    pokemon: dict


@dataclass
class LearnResult:
    status: str
    pokemon: dict | None = None
    move: str = ""
    forgotten: str | None = None


def at_max_level(pokemon: dict) -> bool:
    return pokemon["level"] >= experience.MAX_LEVEL


def _candy_reward(pokemon: dict) -> dict:
    target = experience.exp_for_level(pokemon["dex_id"], pokemon["level"] + 1)
    return {
        "id": new_id(),
        "pokemon_id": str(pokemon["_id"]),
        "exp": target - creatures.current_exp(pokemon),
        "evs": [0] * len(experience.STAT_NAMES),
    }


async def give(stores: Stores, trainer_id: int, pokemon_id: str) -> CandyResult:
    trainer = await stores.trainers.get(trainer_id)
    if trainer is None:
        return CandyResult(GONE)
    await settle_pending(stores, trainer_id, trainer)
    pokemon = await stores.pokemon.get(trainer_id, pokemon_id)
    if pokemon is None:
        return CandyResult(GONE)
    if at_max_level(pokemon):
        return CandyResult(MAX_LEVEL, pokemon)

    reward = _candy_reward(pokemon)
    if not await stores.trainers.spend_candy(trainer_id, reward, BATTLE_IDLE_SECONDS):
        return CandyResult(await _refusal(stores, trainer_id), pokemon)
    gains = await settle_pending(stores, trainer_id)
    gain = next((gain for gain in gains if str(gain.pokemon["_id"]) == pokemon_id), None)
    if gain is None:
        return CandyResult(FAILED, pokemon)

    new_level = gain.new_level
    ready = evolving.readiness({**pokemon, "level": new_level}, trainer["region"]) == evolving.READY
    return CandyResult(GAVE, pokemon, gain.old_level, new_level, gain.learned, gain.waiting, ready)


def can_take_more(result: CandyResult) -> bool:
    return result.new_level < experience.MAX_LEVEL


async def _refusal(stores: Stores, trainer_id: int) -> str:
    if await stores.trainers.in_trade(trainer_id):
        return IN_TRADE
    if await stores.trainers.in_battle(trainer_id, BATTLE_IDLE_SECONDS):
        return IN_BATTLE
    trainer = await stores.trainers.get(trainer_id)
    return NO_CANDY if trainer.get("items", {}).get("rare_candy", 0) < 1 else FAILED


def new_prompt_id() -> str:
    return new_id()


async def remember_prompt(
    stores: Stores,
    trainer_id: int,
    prompt_id: str,
    pokemon_id: str,
    move: str,
    chat_id: int,
    message_id: int,
) -> None:
    await stores.trainers.add_move_prompt(
        trainer_id,
        {
            "id": prompt_id,
            "pokemon_id": pokemon_id,
            "move": move,
            "message": {"chat_id": chat_id, "message_id": message_id},
            "expires_at": datetime.now(timezone.utc) + timedelta(seconds=PROMPT_SECONDS),
        },
    )


async def prompt_view(stores: Stores, trainer_id: int, prompt_id: str) -> PromptView | None:
    trainer = await stores.trainers.get(trainer_id)
    prompts = trainer.get("move_prompts", []) if trainer else []
    prompt = next((entry for entry in prompts if entry["id"] == prompt_id), None)
    if prompt is None:
        return None
    pokemon = await stores.pokemon.get(trainer_id, prompt["pokemon_id"])
    return PromptView(prompt, pokemon) if pokemon else None


async def learn(stores: Stores, trainer_id: int, prompt_id: str, forgotten: int | None) -> LearnResult:
    view = await prompt_view(stores, trainer_id, prompt_id)
    if view is None:
        return LearnResult(EXPIRED)
    pokemon, move = view.pokemon, view.prompt["move"]
    moves = pokemon["moves"]
    if forgotten is None and len(moves) >= pokedex.MAX_MOVES and move not in moves:
        return LearnResult(NEEDS_FORGET, pokemon, move)
    if forgotten is not None and not 0 <= forgotten < len(moves):
        return LearnResult(FAILED, pokemon, move)

    if not await stores.trainers.claim_move_prompt(trainer_id, prompt_id, BATTLE_IDLE_SECONDS):
        status = await _refusal(stores, trainer_id)
        return LearnResult(status if status in (IN_BATTLE, IN_TRADE) else EXPIRED, pokemon, move)
    if move in moves:
        return LearnResult(FAILED, pokemon, move)
    after = teaching_rules.after_teaching(moves, move, forgotten)
    if not await stores.pokemon.replace_moves(trainer_id, str(pokemon["_id"]), moves, after):
        return LearnResult(FAILED, pokemon, move)
    return LearnResult(LEARNED, pokemon, move, moves[forgotten] if forgotten is not None else None)


async def decline(stores: Stores, trainer_id: int, prompt_id: str) -> LearnResult:
    view = await prompt_view(stores, trainer_id, prompt_id)
    if view is None or not await stores.trainers.drop_move_prompt(trainer_id, prompt_id):
        return LearnResult(EXPIRED)
    return LearnResult(LEARNED, view.pokemon, view.prompt["move"])


async def next_expired_prompts(stores: Stores) -> list[tuple[dict, dict | None]] | None:
    claimed = await stores.trainers.claim_expired_move_prompts()
    if claimed is None:
        return None
    trainer_id, prompts = claimed
    return [(prompt, await stores.pokemon.get(trainer_id, prompt["pokemon_id"])) for prompt in prompts]
