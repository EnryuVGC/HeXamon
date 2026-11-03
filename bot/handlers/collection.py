from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from bot.handlers.journey import JourneyRequired
from bot.handlers.private import private_only
from bot.services import collection
from bot.storage.stores import Stores
from bot.ui import collection_view, pokemon_list
from bot.ui.keyboards import (
    COLLECTION_SCREEN,
    DisplayAction,
    PageSizeAction,
    SortAction,
    display_keyboard,
    page_size_keyboard,
    sort_keyboard,
)
from bot.ui.pokemon_list import PokemonListPage
from bot.ui.texts import text

router = Router()
router.message.middleware(JourneyRequired())


async def _is_owner(callback: CallbackQuery, owner_id: int) -> bool:
    if callback.from_user.id == owner_id and isinstance(callback.message, Message):
        return True
    await callback.answer(text("common.not_your_buttons"), show_alert=True)
    return False


async def _show(callback: CallbackQuery, body: str, markup: InlineKeyboardMarkup) -> None:
    try:
        await callback.message.edit_text(body, reply_markup=markup)
    except TelegramBadRequest as error:
        if "message is not modified" not in str(error):
            raise


@router.message(Command("mypokemon"), F.from_user)
async def mypokemon_command(message: Message, stores: Stores) -> None:
    trainer_id = message.from_user.id
    page = await collection.first_page(stores, trainer_id)
    if page is None:
        await message.reply(text("common.start_journey"))
        return
    await message.reply(
        collection_view.collection_text(page),
        reply_markup=pokemon_list.keyboard(trainer_id, COLLECTION_SCREEN, page.page),
    )


@router.callback_query(PokemonListPage.filter(F.screen == COLLECTION_SCREEN))
async def collection_page_turned(
    callback: CallbackQuery,
    callback_data: PokemonListPage,
    stores: Stores,
) -> None:
    if not await _is_owner(callback, callback_data.owner_id):
        return
    page = await collection.turn_page(
        stores,
        callback.from_user.id,
        callback_data.page,
        callback_data.delta,
        callback_data.anchor,
    )
    await callback.answer()
    if page is not None and page.page.pokemon:
        await _show(
            callback,
            collection_view.collection_text(page),
            pokemon_list.keyboard(callback.from_user.id, COLLECTION_SCREEN, page.page),
        )


@router.message(Command("sort"), F.from_user)
@private_only("sort")
async def sort_command(message: Message, stores: Stores) -> None:
    trainer_id = message.from_user.id
    sort = await collection.current_sort(stores, trainer_id)
    if sort is None:
        await message.reply(text("common.start_journey"))
        return
    await message.reply(collection_view.sort_text(sort), reply_markup=sort_keyboard(trainer_id))


@router.callback_query(SortAction.filter())
async def sort_pressed(callback: CallbackQuery, callback_data: SortAction, stores: Stores) -> None:
    if not await _is_owner(callback, callback_data.owner_id):
        return
    trainer_id = callback.from_user.id
    if callback_data.key == SortAction.CHANGE_DIRECTION:
        sort = await collection.change_direction(stores, trainer_id)
    else:
        sort = await collection.choose_sort(stores, trainer_id, callback_data.key)
    await callback.answer()
    if sort is not None:
        await _show(callback, collection_view.sort_text(sort), sort_keyboard(trainer_id))


@router.message(Command("display"), F.from_user)
@private_only("display")
async def display_command(message: Message, stores: Stores) -> None:
    trainer_id = message.from_user.id
    display = await collection.current_display(stores, trainer_id)
    if display is None:
        await message.reply(text("common.start_journey"))
        return
    await message.reply(collection_view.display_text(display), reply_markup=display_keyboard(trainer_id))


@router.callback_query(DisplayAction.filter())
async def display_pressed(callback: CallbackQuery, callback_data: DisplayAction, stores: Stores) -> None:
    if not await _is_owner(callback, callback_data.owner_id):
        return
    trainer_id = callback.from_user.id
    if callback_data.key == DisplayAction.TOGGLE_NUMBERS:
        display = await collection.toggle_numbers(stores, trainer_id)
    else:
        display = await collection.choose_display(stores, trainer_id, callback_data.key)
    await callback.answer()
    if display is not None:
        await _show(callback, collection_view.display_text(display), display_keyboard(trainer_id))


@router.message(Command("pagesize"), F.from_user)
@private_only("pagesize")
async def pagesize_command(message: Message, stores: Stores) -> None:
    trainer_id = message.from_user.id
    size = await collection.current_page_size(stores, trainer_id)
    if size is None:
        await message.reply(text("common.start_journey"))
        return
    await message.reply(text("page_size.menu", size=size), reply_markup=page_size_keyboard(trainer_id))


@router.callback_query(PageSizeAction.filter())
async def pagesize_pressed(callback: CallbackQuery, callback_data: PageSizeAction, stores: Stores) -> None:
    if not await _is_owner(callback, callback_data.owner_id):
        return
    trainer_id = callback.from_user.id
    size = await collection.choose_page_size(stores, trainer_id, callback_data.size)
    await callback.answer()
    if size is not None:
        await _show(callback, text("page_size.menu", size=size), page_size_keyboard(trainer_id))
