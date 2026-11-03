import re

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, Message

from bot.handlers.journey import JourneyRequired
from bot.services import tms
from bot.storage.stores import Stores
from bot.ui import tm_view
from bot.ui.keyboards import (
    TM_BACK,
    TM_BUY,
    TM_CANCEL,
    TM_CONFIRM_SELL,
    TM_FORGET,
    TM_LEARNERS_BACK,
    TM_PICK,
    TM_SCREEN_PREFIX,
    TM_SELL,
    TM_USE,
    TmAction,
)
from bot.ui.pokemon_list import PokemonListPage
from bot.ui.texts import text

router = Router()
router.message.middleware(JourneyRequired())

TM_COMMAND = re.compile(r"^tm(\d+)$", re.IGNORECASE)
TEACH_REFUSALS = {
    tms.CANNOT_LEARN: "tm.cannot_learn",
    tms.NO_TM: "tm.no_tm",
    tms.GONE: "pokemon_picker.gone",
    tms.IN_BATTLE: "hunt.already_in_battle",
    tms.IN_TRADE: "trade.locked",
    tms.FAILED: "tm.teach_failed",
}


async def _is_owner(callback: CallbackQuery, owner_id: int) -> bool:
    if callback.from_user.id == owner_id and isinstance(callback.message, Message):
        return True
    await callback.answer(text("common.not_your_buttons"), show_alert=True)
    return False


async def _show(callback: CallbackQuery, body: str, markup=None) -> None:
    try:
        await callback.message.edit_text(body, reply_markup=markup)
    except TelegramBadRequest as error:
        if "message is not modified" not in str(error):
            raise


async def _show_card(callback: CallbackQuery, stores: Stores, number: int) -> None:
    card = await tms.card(stores, callback.from_user.id, number)
    await callback.answer()
    if card is not None:
        await _show(callback, tm_view.card_text(card), tm_view.card_keyboard(callback.from_user.id, card))


async def _show_learners(callback: CallbackQuery, stores: Stores, number: int) -> None:
    trainer_id = callback.from_user.id
    if not await tms.owns(stores, trainer_id, number):
        await callback.answer(text("tm.no_tm"), show_alert=True)
        return
    card = await tms.card(stores, trainer_id, number)
    page = await tms.first_learners_page(stores, trainer_id, number)
    if card is None or page is None:
        await callback.answer(text("tm.no_tm"), show_alert=True)
        return
    if not page.pokemon:
        await callback.answer(text("tm.no_learners"), show_alert=True)
        return
    await callback.answer()
    await _show(callback, tm_view.learners_text(card.move, page), tm_view.learners_keyboard(trainer_id, number, page))


@router.message(Command(TM_COMMAND), F.from_user)
async def tm_command(message: Message, command: CommandObject, stores: Stores) -> None:
    trainer_id = message.from_user.id
    card = await tms.card(stores, trainer_id, int(command.regexp_match.group(1)))
    if card is None:
        await message.reply(text("tm.unknown"))
        return
    if not card.owned and not card.in_store:
        await message.reply(text("tm.not_owned", number=card.number))
        return
    await message.reply(tm_view.card_text(card), reply_markup=tm_view.card_keyboard(trainer_id, card))


@router.callback_query(TmAction.filter(F.action == TM_BUY))
async def buy_pressed(callback: CallbackQuery, callback_data: TmAction, stores: Stores) -> None:
    if not await _is_owner(callback, callback_data.owner_id):
        return
    status, price = await tms.buy(stores, callback.from_user.id, callback_data.number)
    if status != tms.BOUGHT:
        await callback.answer(text(f"tm.{status}"), show_alert=True)
        return
    await callback.answer()
    await _show(callback, text("tm.purchased", number=callback_data.number, price=price))


@router.callback_query(TmAction.filter(F.action == TM_SELL))
async def sell_pressed(callback: CallbackQuery, callback_data: TmAction, stores: Stores) -> None:
    if not await _is_owner(callback, callback_data.owner_id):
        return
    card = await tms.card(stores, callback.from_user.id, callback_data.number)
    if card is None or not card.owned:
        await callback.answer(text("tm.no_tm"), show_alert=True)
        return
    await callback.answer()
    await _show(
        callback,
        text("tm.sell_confirm", number=card.number, price=card.sell_price),
        tm_view.sell_confirm_keyboard(callback.from_user.id, card.number),
    )


@router.callback_query(TmAction.filter(F.action == TM_CONFIRM_SELL))
async def sell_confirmed(callback: CallbackQuery, callback_data: TmAction, stores: Stores) -> None:
    if not await _is_owner(callback, callback_data.owner_id):
        return
    price = await tms.sell(stores, callback.from_user.id, callback_data.number)
    if price is None:
        await callback.answer(text("tm.no_tm"), show_alert=True)
        return
    await callback.answer()
    await _show(callback, text("tm.sold", number=callback_data.number, price=price))


@router.callback_query(TmAction.filter(F.action.in_({TM_CANCEL, TM_BACK})))
async def back_to_card(callback: CallbackQuery, callback_data: TmAction, stores: Stores) -> None:
    if await _is_owner(callback, callback_data.owner_id):
        await _show_card(callback, stores, callback_data.number)


@router.callback_query(TmAction.filter(F.action.in_({TM_USE, TM_LEARNERS_BACK})))
async def use_pressed(callback: CallbackQuery, callback_data: TmAction, stores: Stores) -> None:
    if await _is_owner(callback, callback_data.owner_id):
        await _show_learners(callback, stores, callback_data.number)


@router.callback_query(PokemonListPage.filter(F.screen.startswith(TM_SCREEN_PREFIX)))
async def learners_page_turned(callback: CallbackQuery, callback_data: PokemonListPage, stores: Stores) -> None:
    if not await _is_owner(callback, callback_data.owner_id):
        return
    trainer_id = callback.from_user.id
    number = int(callback_data.screen.removeprefix(TM_SCREEN_PREFIX))
    card = await tms.card(stores, trainer_id, number)
    page = await tms.turn_learners_page(
        stores, trainer_id, number, callback_data.page, callback_data.delta, callback_data.anchor
    )
    await callback.answer()
    if card is not None and page is not None and page.pokemon:
        await _show(callback, tm_view.learners_text(card.move, page), tm_view.learners_keyboard(trainer_id, number, page))


@router.callback_query(TmAction.filter(F.action.in_({TM_PICK, TM_FORGET})))
async def teach_pressed(callback: CallbackQuery, callback_data: TmAction, stores: Stores) -> None:
    if not await _is_owner(callback, callback_data.owner_id):
        return
    trainer_id = callback.from_user.id
    forgotten = callback_data.slot if callback_data.action == TM_FORGET else None
    result = await tms.teach(stores, trainer_id, callback_data.number, callback_data.pokemon_id, forgotten)
    if result.status in TEACH_REFUSALS:
        await callback.answer(text(TEACH_REFUSALS[result.status]), show_alert=True)
        return
    await callback.answer()
    if result.status == tms.NEEDS_FORGET:
        await _show(
            callback,
            tm_view.forget_text(result.pokemon, result.move),
            tm_view.forget_keyboard(trainer_id, callback_data.number, result.pokemon),
        )
        return
    await _show(callback, tm_view.taught_text(result))
