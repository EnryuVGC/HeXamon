from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, InputMediaPhoto, Message, ReplyParameters

from bot.game import pokedex_entries as rules
from bot.handlers.journey import JourneyRequired
from bot.services import pokedex_entries, pokedex_list
from bot.storage.stores import Stores
from bot.ui import battle_view, pokedex_view
from bot.ui.keyboards import (
    PokedexEntry,
    PokedexPage,
    PokedexPageTurn,
    PokedexSuggestion,
    pokedex_keyboard,
    pokedex_page_keyboard,
    pokedex_suggestion_keyboard,
)
from bot.ui.texts import text

router = Router()
router.message.middleware(JourneyRequired())


@router.message(Command("pokedex"), F.from_user)
async def pokedex_command(message: Message, command: CommandObject, stores: Stores) -> None:
    if not command.args:
        await message.reply(text("pokedex.usage"))
        return
    trainer_id = message.from_user.id
    result = await pokedex_entries.search(stores, trainer_id, command.args)
    if result is None:
        await message.reply(text("pokedex.not_found"))
    elif isinstance(result, pokedex_entries.Suggestion):
        await message.reply(
            pokedex_view.suggestion_text(result.dex_id),
            reply_markup=pokedex_suggestion_keyboard(trainer_id, result.dex_id),
        )
    else:
        await _send_entry(message, trainer_id, result, message.message_id)


async def _send_entry(message: Message, trainer_id: int, dex_id: int, quoted_id: int | None) -> None:
    caption = pokedex_view.page_text(dex_id, rules.ABOUT)
    markup = pokedex_page_keyboard(trainer_id, dex_id, rules.ABOUT)
    quoted = ReplyParameters(message_id=quoted_id, allow_sending_without_reply=True) if quoted_id else None
    try:
        await message.answer_photo(
            battle_view.artwork(dex_id),
            caption=caption,
            reply_markup=markup,
            reply_parameters=quoted,
        )
    except TelegramBadRequest:
        await message.answer(caption, reply_markup=markup, reply_parameters=quoted)


async def _delete(message: Message) -> None:
    try:
        await message.delete()
    except TelegramBadRequest:
        pass


@router.callback_query(PokedexSuggestion.filter())
async def suggestion_answered(callback: CallbackQuery, callback_data: PokedexSuggestion, stores: Stores) -> None:
    trainer_id = callback.from_user.id
    prompt = callback.message
    if trainer_id != callback_data.owner_id or not isinstance(prompt, Message):
        await callback.answer(text("common.not_your_buttons"), show_alert=True)
        return
    if callback_data.accepted and not await pokedex_entries.can_view(stores, trainer_id, callback_data.dex_id):
        await callback.answer(text("pokedex.not_found"), show_alert=True)
        return
    await callback.answer()
    if callback_data.accepted:
        quoted_id = prompt.reply_to_message.message_id if prompt.reply_to_message else None
        await _send_entry(prompt, trainer_id, callback_data.dex_id, quoted_id)
    await _delete(prompt)


async def _show_page(callback: CallbackQuery, callback_data: PokedexPage) -> None:
    dex_id, view = callback_data.dex_id, callback_data.view
    caption = pokedex_view.page_text(dex_id, view)
    markup = pokedex_page_keyboard(callback.from_user.id, dex_id, view)
    message = callback.message
    if not message.photo:
        await message.edit_text(caption, reply_markup=markup)
        return
    if callback_data.turned:
        try:
            media = InputMediaPhoto(media=battle_view.artwork(dex_id), caption=caption)
            await message.edit_media(media, reply_markup=markup)
            return
        except TelegramBadRequest:
            pass
    await message.edit_caption(caption=caption, reply_markup=markup)


@router.callback_query(PokedexPage.filter())
async def entry_page_pressed(callback: CallbackQuery, callback_data: PokedexPage, stores: Stores) -> None:
    trainer_id = callback.from_user.id
    if trainer_id != callback_data.owner_id or not isinstance(callback.message, Message):
        await callback.answer(text("common.not_your_buttons"), show_alert=True)
        return
    if not await pokedex_entries.can_view(stores, trainer_id, callback_data.dex_id):
        await callback.answer(text("pokedex.not_found"), show_alert=True)
        return
    try:
        await _show_page(callback, callback_data)
    except TelegramBadRequest as error:
        if "message is not modified" not in str(error):
            raise
    finally:
        await callback.answer()


@router.message(Command("pokedexall"), F.from_user)
async def pokedexall_command(message: Message, stores: Stores) -> None:
    trainer_id = message.from_user.id
    page = await pokedex_list.page_of(stores, trainer_id, 1)
    if page is None:
        await message.reply(text("common.start_journey"))
        return
    await message.reply(
        pokedex_view.list_text(page),
        reply_markup=pokedex_keyboard(trainer_id, page.page, page.pages),
    )


@router.callback_query(PokedexPageTurn.filter())
async def page_turned(callback: CallbackQuery, callback_data: PokedexPageTurn, stores: Stores) -> None:
    trainer_id = callback.from_user.id
    if trainer_id != callback_data.owner_id or not isinstance(callback.message, Message):
        await callback.answer(text("common.not_your_buttons"), show_alert=True)
        return
    page = await pokedex_list.page_of(stores, trainer_id, callback_data.page)
    await callback.answer()
    if page is None:
        return
    try:
        await callback.message.edit_text(
            pokedex_view.list_text(page),
            reply_markup=pokedex_keyboard(trainer_id, page.page, page.pages),
        )
    except TelegramBadRequest as error:
        if "message is not modified" not in str(error):
            raise


@router.callback_query(PokedexEntry.filter())
async def entry_pressed(callback: CallbackQuery, callback_data: PokedexEntry) -> None:
    await callback.answer()
    if not isinstance(callback.message, Message):
        return
    await _send_entry(callback.message, callback.from_user.id, callback_data.dex_id, callback.message.message_id)
