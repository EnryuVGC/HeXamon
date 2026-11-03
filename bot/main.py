import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer

from bot.core.config import load_settings
from bot.handlers import (
    admin,
    boost,
    candy,
    card,
    challenge,
    collection,
    commands,
    eggs,
    ev_items,
    ev_training,
    events,
    evolve,
    give,
    guess,
    hunt,
    inventory,
    key_items,
    keyboard,
    lottery,
    mystats,
    nickname,
    pokeballs,
    pokedex,
    pokemon_list,
    pokemon_picker,
    private,
    referrals,
    release,
    safari,
    song,
    start,
    stats,
    store,
    team,
    tms,
    trade,
    travel,
)
from bot.services import tm_renumbering
from bot.storage.mongo import open_client
from bot.storage.stores import Stores


async def run() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = load_settings()

    client = open_client(settings.mongo_uri)
    database = client[settings.mongo_database]
    await database.command("ping")
    stores = Stores.of(database)
    await stores.ensure_indexes()
    await tm_renumbering.run(stores)

    session = AiohttpSession(api=TelegramAPIServer.from_base(settings.bot_api_url)) if settings.bot_api_url else None
    bot = Bot(settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML), session=session)
    dispatcher = Dispatcher(stores=stores, admin_ids=settings.admin_ids)
    dispatcher.message.outer_middleware(admin.BannedUsers())
    dispatcher.callback_query.outer_middleware(admin.BannedUsers())
    dispatcher.message.outer_middleware(guess.GuessAnswers())
    dispatcher.include_router(private.router)
    dispatcher.include_router(admin.public_router)
    dispatcher.include_router(admin.router)
    dispatcher.include_router(candy.offer_link_router)
    dispatcher.include_router(start.router)
    dispatcher.include_router(hunt.router)
    dispatcher.include_router(team.router)
    dispatcher.include_router(pokemon_list.router)
    dispatcher.include_router(collection.router)
    dispatcher.include_router(pokemon_picker.router)
    dispatcher.include_router(stats.router)
    dispatcher.include_router(release.router)
    dispatcher.include_router(pokedex.router)
    dispatcher.include_router(trade.router)
    dispatcher.include_router(challenge.router)
    dispatcher.include_router(give.router)
    dispatcher.include_router(inventory.router)
    dispatcher.include_router(key_items.router)
    dispatcher.include_router(mystats.router)
    dispatcher.include_router(card.router)
    dispatcher.include_router(travel.router)
    dispatcher.include_router(guess.router)
    dispatcher.include_router(events.router)
    dispatcher.include_router(song.router)
    dispatcher.include_router(commands.router)
    dispatcher.include_router(referrals.router)
    dispatcher.include_router(lottery.router)
    dispatcher.include_router(safari.router)
    dispatcher.include_router(ev_training.router)
    dispatcher.include_router(pokeballs.router)
    dispatcher.include_router(store.router)
    dispatcher.include_router(tms.router)
    dispatcher.include_router(evolve.router)
    dispatcher.include_router(candy.router)
    dispatcher.include_router(ev_items.router)
    dispatcher.include_router(boost.router)
    dispatcher.include_router(keyboard.router)
    dispatcher.include_router(nickname.router)

    flee_task = asyncio.create_task(hunt.flee_idle_encounters(stores))
    trade_task = asyncio.create_task(trade.finish_idle_trades(bot, stores))
    prompt_task = asyncio.create_task(candy.expire_move_prompts(bot, stores))
    challenge_task = asyncio.create_task(challenge.finish_idle_challenges(bot, stores))
    referral_task = asyncio.create_task(referrals.pay_referrals(bot, stores))
    lottery_task = asyncio.create_task(lottery.run_draws(bot, stores))
    egg_task = asyncio.create_task(eggs.hatch_eggs(bot, stores))
    try:
        await dispatcher.start_polling(bot)
    finally:
        flee_task.cancel()
        trade_task.cancel()
        prompt_task.cancel()
        challenge_task.cancel()
        referral_task.cancel()
        lottery_task.cancel()
        egg_task.cancel()
        client.close()


if __name__ == "__main__":
    asyncio.run(run())
