from bot.storage.stores import Stores


async def mark_open(stores: Stores, trainer_id: int) -> bool:
    return await stores.trainers.open_reply_keyboard(trainer_id)


async def mark_closed(stores: Stores, trainer_id: int) -> None:
    await stores.trainers.close_reply_keyboard(trainer_id)
