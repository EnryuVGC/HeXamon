from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, Message

from bot.handlers.journey import JourneyRequired
from bot.services import store
from bot.storage.stores import Stores
from bot.ui import store_view
from bot.ui.keyboards import STORE_BALLS, STORE_TMS, StorePage, store_keyboard
from bot.ui.texts import text

router = Router()
router.message.middleware(JourneyRequired())


@router.message(Command("pokestore"), F.from_user)
async def pokestore_command(message: Message) -> None:
    await message.reply(store_view.items_text(), reply_markup=store_keyboard(message.from_user.id))


@router.message(Command("items"))
async def items_command(message: Message) -> None:
    await message.reply(text("shop.items_info"))


@router.message(Command("keyitem"), F.from_user)
async def key_items_command(message: Message) -> None:
    await message.reply(store_view.key_items_text(), reply_markup=store_keyboard(message.from_user.id))


@router.message(Command("buy"), F.from_user)
async def buy_command(message: Message, command: CommandObject, stores: Stores) -> None:
    result = await store.buy(stores, message.from_user.id, command.args)
    if result.status == store.DONE:
        await message.reply(store_view.purchased_text(result))
    else:
        await message.reply(text(f"shop.{result.status}", command="buy"))


@router.message(Command("sell"), F.from_user)
async def sell_command(message: Message, command: CommandObject, stores: Stores) -> None:
    result = await store.sell(stores, message.from_user.id, command.args)
    if result.status == store.DONE:
        await message.reply(store_view.sold_text(result))
    else:
        await message.reply(text(f"shop.{result.status}", command="sell"))


@router.message(Command("buyinfo"))
async def buy_info_command(message: Message) -> None:
    await message.reply(text("shop.buy_info"))


@router.message(Command("sellinfo"))
async def sell_info_command(message: Message) -> None:
    await message.reply(text("shop.sell_info"))


@router.callback_query(StorePage.filter())
async def page_pressed(callback: CallbackQuery, callback_data: StorePage, stores: Stores) -> None:
    trainer_id = callback.from_user.id
    if trainer_id != callback_data.owner_id or not isinstance(callback.message, Message):
        await callback.answer(text("common.not_your_buttons"), show_alert=True)
        return
    await callback.answer()
    if callback_data.page == STORE_BALLS:
        body = store_view.balls_text()
    elif callback_data.page == STORE_TMS:
        body = store_view.tms_text(await store.available_tms(stores, trainer_id))
    else:
        body = store_view.items_text()
    try:
        await callback.message.edit_text(body, reply_markup=store_keyboard(trainer_id, callback_data.page))
    except TelegramBadRequest as error:
        if "message is not modified" not in str(error):
            raise
