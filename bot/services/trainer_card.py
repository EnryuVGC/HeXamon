import asyncio

from bot.game import card_styles as rules
from bot.services.trainer_stats import stats_of
from bot.storage.stores import Stores
from bot.ui import trainer_card


async def saved_style(stores: Stores, trainer_id: int) -> rules.CardStyle | None:
    trainer = await stores.trainers.get(trainer_id)
    return rules.style_of(trainer) if trainer else None


async def card_image(stores: Stores, trainer_id: int, style: rules.CardStyle | None = None) -> bytes | None:
    trainer = await stores.trainers.get(trainer_id)
    stats = await stats_of(stores, trainer_id)
    if trainer is None or stats is None:
        return None
    return await asyncio.to_thread(trainer_card.render, stats, style or rules.style_of(trainer))


async def template_grid() -> bytes:
    return await asyncio.to_thread(trainer_card.template_grid)


async def save_choice(stores: Stores, trainer_id: int, field: str, value: int) -> None:
    if rules.valid(field, value):
        await stores.trainers.set_card_choice(trainer_id, field, value)


async def save_custom_color(stores: Stores, trainer_id: int, color: str) -> None:
    await stores.trainers.set_card_choice(trainer_id, rules.TEXT, color)
