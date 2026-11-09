from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, Message

from bot.game import inventory as inventory_rules
from bot.game import store as rules
from bot.game.paging import clamp_page, page_count
from bot.handlers.journey import JourneyRequired
from bot.services import store
from bot.storage.stores import Stores
from bot.ui import store_view
from bot.ui.keyboards import (
    KEY_SELL_CANCEL,
    KEY_SELL_CONFIRM,
    KEY_SELL_LIST,
    KEY_SELL_PICK,
    STORE_BALLS,
    STORE_TMS,
    KeyItemSale,
    StorePage,
    store_keyboard,
)
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


async def _edit(message: Message, body: str, markup=None) -> None:
    try:
        await message.edit_text(body, reply_markup=markup)
    except TelegramBadRequest as error:
        if "message is not modified" not in str(error):
            raise


def _key_item_list(trainer_id: int, stones: list[str], page: int):
    if not stones:
        return text("shop.no_key_items"), None
    pages = page_count(len(stones), rules.KEY_ITEMS_PER_PAGE)
    page = clamp_page(page, pages)
    return store_view.key_item_list_text(page, pages), store_view.key_item_list_keyboard(trainer_id, stones, page)


async def _sell_key_item_command(message: Message, command: CommandObject, stores: Stores) -> bool:
    trainer_id = message.from_user.id
    if rules.is_key_item_request(command.args):
        body, markup = _key_item_list(trainer_id, await store.owned_key_items(stores, trainer_id), 1)
        await message.reply(body, reply_markup=markup)
        return True
    stone = inventory_rules.stone_named(command.args)
    if stone is None:
        return False
    if stone not in await store.owned_key_items(stores, trainer_id):
        await message.reply(text("shop.key_item_not_owned"))
        return True
    await message.reply(
        store_view.key_item_confirm_text(stone),
        reply_markup=store_view.key_item_confirm_keyboard(trainer_id, stone, 1),
    )
    return True


@router.message(Command("sell"), F.from_user)
async def sell_command(message: Message, command: CommandObject, stores: Stores) -> None:
    if rules.parse_order(command.args) is None and await _sell_key_item_command(message, command, stores):
        return
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


@router.callback_query(KeyItemSale.filter())
async def key_item_sale_pressed(callback: CallbackQuery, callback_data: KeyItemSale, stores: Stores) -> None:
    trainer_id = callback.from_user.id
    if trainer_id != callback_data.owner_id or not isinstance(callback.message, Message):
        await callback.answer(text("common.not_your_buttons"), show_alert=True)
        return
    action = callback_data.action
    if action == KEY_SELL_CANCEL:
        await callback.answer()
        await _edit(callback.message, text("shop.key_item_cancelled"))
        return
    if action == KEY_SELL_LIST:
        await callback.answer()
        stones = await store.owned_key_items(stores, trainer_id)
        await _edit(callback.message, *_key_item_list(trainer_id, stones, callback_data.page))
        return
    stone = inventory_rules.stone_at(callback_data.stone)
    if stone is None:
        await callback.answer(text("shop.key_item_not_owned"), show_alert=True)
        return
    if action == KEY_SELL_PICK:
        if stone not in await store.owned_key_items(stores, trainer_id):
            await callback.answer(text("shop.key_item_not_owned"), show_alert=True)
            return
        await callback.answer()
        await _edit(
            callback.message,
            store_view.key_item_confirm_text(stone),
            store_view.key_item_confirm_keyboard(trainer_id, stone, callback_data.page),
        )
        return
    if action == KEY_SELL_CONFIRM:
        status = await store.sell_key_item(stores, trainer_id, stone)
        if status != store.DONE:
            await callback.answer(text(f"shop.{status}"), show_alert=True)
            return
        await callback.answer()
        await _edit(callback.message, store_view.key_item_sold_text(stone))


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
