from aiogram import Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, Message, ReplyParameters

from bot.game import creatures
from bot.game.stats_pages import INFO, is_valid_page
from bot.handlers.pokemon_picker import pokemon_command
from bot.services import pokemon_search
from bot.storage.stores import Stores
from bot.ui import battle_view, stats_view
from bot.ui.keyboards import StatsOpen, StatsPage, stats_keyboard
from bot.ui.texts import text

router = Router()


async def _is_owner(callback: CallbackQuery, owner_id: int) -> bool:
    if callback.from_user.id == owner_id and isinstance(callback.message, Message):
        return True
    await callback.answer(text("common.not_your_buttons"), show_alert=True)
    return False


def _quoting(message_id: int | None) -> ReplyParameters | None:
    if message_id is None:
        return None
    return ReplyParameters(message_id=message_id, allow_sending_without_reply=True)


@pokemon_command("stats", code="st")
async def send_info_page(
    message: Message,
    owner_id: int,
    pokemon: dict,
    quoted_id: int | None,
    stores: Stores,
) -> None:
    caption = stats_view.page_text(INFO, pokemon)
    markup = stats_keyboard(owner_id, str(pokemon["_id"]), INFO)
    try:
        await message.answer_photo(
            battle_view.artwork(creatures.form_id(pokemon), pokemon.get("shiny", False)),
            caption=caption,
            reply_markup=markup,
            reply_parameters=_quoting(quoted_id),
        )
    except TelegramBadRequest:
        await message.answer(caption, reply_markup=markup, reply_parameters=_quoting(quoted_id))


@pokemon_command("inspect", code="in")
async def send_inspection(
    message: Message,
    owner_id: int,
    pokemon: dict,
    quoted_id: int | None,
    stores: Stores,
) -> None:
    await message.answer(stats_view.inspect_text(pokemon), reply_parameters=_quoting(quoted_id))


async def _edit_text(message: Message, body: str, markup) -> None:
    try:
        await message.edit_text(body, reply_markup=markup)
    except TelegramBadRequest as error:
        if "message is not modified" not in str(error):
            raise


async def _edit_page(message: Message, body: str, markup) -> None:
    if not message.photo:
        await _edit_text(message, body, markup)
        return
    try:
        await message.edit_caption(caption=body, reply_markup=markup)
    except TelegramBadRequest as error:
        if "message is not modified" not in str(error):
            raise


@router.callback_query(StatsOpen.filter())
async def stats_opened(callback: CallbackQuery, callback_data: StatsOpen, stores: Stores) -> None:
    if not await _is_owner(callback, callback_data.owner_id):
        return
    trainer_id = callback.from_user.id
    pokemon = await pokemon_search.pokemon_of(stores, trainer_id, callback_data.pokemon_id)
    if pokemon is None:
        await callback.answer(text("pokemon_picker.gone"), show_alert=True)
        return
    await callback.answer()
    await send_info_page(callback.message, trainer_id, pokemon, callback.message.message_id, stores)


@router.callback_query(StatsPage.filter())
async def page_pressed(callback: CallbackQuery, callback_data: StatsPage, stores: Stores) -> None:
    if not await _is_owner(callback, callback_data.owner_id):
        return
    pokemon = await pokemon_search.pokemon_of(stores, callback.from_user.id, callback_data.pokemon_id)
    if pokemon is None or not is_valid_page(callback_data.page):
        await callback.answer(text("pokemon_picker.gone"), show_alert=True)
        return
    await callback.answer()
    await _edit_page(
        callback.message,
        stats_view.page_text(callback_data.page, pokemon),
        stats_keyboard(callback.from_user.id, callback_data.pokemon_id, callback_data.page),
    )
