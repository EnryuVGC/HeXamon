from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from bot.game import inventory as rules
from bot.game.paging import clamp_page
from bot.handlers.journey import JourneyRequired
from bot.services.inventory import inventory_of
from bot.storage.stores import Stores
from bot.ui import inventory_view
from bot.ui.keyboards import (
    INVENTORY_KEY_ITEMS,
    INVENTORY_TMS,
    InventoryPage,
    inventory_key_items_keyboard,
    inventory_main_keyboard,
    inventory_tms_keyboard,
)
from bot.ui.texts import text

router = Router()
router.message.middleware(JourneyRequired())


@router.message(Command("myinventory"), F.from_user)
async def myinventory_command(message: Message, stores: Stores) -> None:
    trainer_id = message.from_user.id
    inventory = await inventory_of(stores, trainer_id)
    if inventory is None:
        await message.reply(text("common.start_journey"))
        return
    await message.reply(inventory_view.main_text(inventory), reply_markup=inventory_main_keyboard(trainer_id))


@router.callback_query(InventoryPage.filter())
async def page_pressed(callback: CallbackQuery, callback_data: InventoryPage, stores: Stores) -> None:
    trainer_id = callback.from_user.id
    if trainer_id != callback_data.owner_id or not isinstance(callback.message, Message):
        await callback.answer(text("common.not_your_buttons"), show_alert=True)
        return
    inventory = await inventory_of(stores, trainer_id)
    await callback.answer()
    if inventory is None:
        return
    if callback_data.page == INVENTORY_KEY_ITEMS:
        body = inventory_view.key_items_text(inventory)
        markup = inventory_key_items_keyboard(trainer_id)
    elif callback_data.page == INVENTORY_TMS:
        pages = rules.tm_pages(len(inventory.tms))
        number = clamp_page(callback_data.number, pages)
        body = inventory_view.tms_text(inventory, number)
        markup = inventory_tms_keyboard(trainer_id, number, pages)
    else:
        body = inventory_view.main_text(inventory)
        markup = inventory_main_keyboard(trainer_id)
    try:
        await callback.message.edit_text(body, reply_markup=markup)
    except TelegramBadRequest as error:
        if "message is not modified" not in str(error):
            raise
