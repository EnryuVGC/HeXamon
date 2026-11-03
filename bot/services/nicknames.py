from bot.game.nicknames import clean_nickname
from bot.game.pokedex import species_name
from bot.services.settling import settle_pending
from bot.storage.stores import Stores


async def pokemon_to_name(stores: Stores, trainer_id: int, pokemon_id: str) -> dict | None:
    await settle_pending(stores, trainer_id)
    pokemon = await stores.pokemon.get(trainer_id, pokemon_id)
    return pokemon if pokemon and pokemon["nickname"] is None else None


async def in_trade(stores: Stores, trainer_id: int) -> bool:
    return await stores.trainers.in_trade(trainer_id)


async def remember_prompt(
    stores: Stores,
    trainer_id: int,
    pokemon_id: str,
    chat_id: int,
    message_id: int,
) -> None:
    await stores.trainers.set_nickname_prompt(trainer_id, pokemon_id, chat_id, message_id)


async def prompt_target(stores: Stores, trainer_id: int, chat_id: int, message_id: int) -> str | None:
    trainer = await stores.trainers.get(trainer_id)
    prompt = trainer.get("nickname_prompt") if trainer else None
    if prompt and prompt["chat_id"] == chat_id and prompt["message_id"] == message_id:
        return prompt["pokemon_id"]
    return None


def validate(raw: str) -> str | None:
    return clean_nickname(raw)


async def save(
    stores: Stores,
    trainer_id: int,
    chat_id: int,
    message_id: int,
    pokemon_id: str,
    nickname: str,
) -> str | None:
    await settle_pending(stores, trainer_id)
    pokemon = await stores.pokemon.set_nickname(trainer_id, pokemon_id, nickname)
    await stores.trainers.clear_nickname_prompt(trainer_id, chat_id, message_id)
    return species_name(pokemon["dex_id"]) if pokemon else None
