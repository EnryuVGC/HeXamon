import asyncio
import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from bot.game import trades as rules
from bot.handlers.hunt import announce_fled
from bot.handlers.journey import JourneyRequired
from bot.services import trading
from bot.storage.stores import Stores
from bot.ui import trade_view
from bot.ui.keyboards import (
    TRADE_SCREEN,
    TradeAction,
    trade_confirm_keyboard,
    trade_pick_keyboard,
    trade_request_keyboard,
)
from bot.ui.pokemon_list import PokemonListPage
from bot.ui.texts import text

router = Router()
router.message.middleware(JourneyRequired())

logger = logging.getLogger(__name__)

EXPIRY_CHECK_SECONDS = 5


async def _show(callback: CallbackQuery, body: str, markup: InlineKeyboardMarkup | None = None) -> None:
    try:
        await callback.message.edit_text(body, reply_markup=markup)
    except TelegramBadRequest as error:
        if "message is not modified" not in str(error):
            raise


async def _ended(callback: CallbackQuery) -> None:
    await callback.answer(text("trade.ended"), show_alert=True)


async def _not_yours(callback: CallbackQuery) -> None:
    await callback.answer(text("common.not_your_buttons"), show_alert=True)


async def _show_stage(callback: CallbackQuery, stores: Stores, trade: dict) -> None:
    if trade["state"] == rules.CONFIRMING:
        offered = await trading.offered_pokemon(stores, trade)
        if offered is None:
            cancelled = await trading.cancel(stores, str(trade["_id"]))
            await _show(callback, text("trade.cancelled") if cancelled else text("trade.ended"))
            return
        await _show(callback, trade_view.confirm_text(trade, offered), trade_confirm_keyboard(str(trade["_id"])))
    elif trade["state"] in rules.CHOOSER_SIDE:
        page = await trading.chooser_page(stores, trade)
        if page is None:
            await _show(callback, text("trade.ended"))
            return
        markup = trade_pick_keyboard(rules.chooser_id(trade), str(trade["_id"]), page.page)
        await _show(callback, trade_view.choose_text(trade, page), markup)
    else:
        await _show(callback, trade_view.result_text(trade))


@router.message(Command("trade"), F.from_user)
async def trade_command(message: Message, stores: Stores) -> None:
    replied = message.reply_to_message
    partner = replied.from_user if replied and not replied.forum_topic_created else None
    if partner is None:
        await message.reply(text("trade.usage"))
        return
    if partner.id == message.from_user.id:
        await message.reply(text("trade.self"))
        return
    if partner.is_bot:
        await message.reply(text("trade.bot"))
        return

    result = await trading.request(
        stores,
        message.from_user.id,
        message.from_user.first_name,
        partner.id,
        partner.first_name,
        message.chat.id,
    )
    if result.status != trading.REQUESTED:
        await message.reply(text(f"trade.{result.status}"))
        return
    trade = await trading.get(stores, result.trade_id)
    sent = await message.reply(trade_view.request_text(trade), reply_markup=trade_request_keyboard(result.trade_id))
    await trading.remember_message(stores, result.trade_id, sent.message_id)


@router.callback_query(TradeAction.filter(F.action == "agree"))
async def agree_pressed(callback: CallbackQuery, callback_data: TradeAction, stores: Stores) -> None:
    trade = await trading.get(stores, callback_data.trade_id)
    if trade is None or trade["state"] != rules.REQUESTED or not isinstance(callback.message, Message):
        await _ended(callback)
        return
    if callback.from_user.id != trade[rules.PARTNER]["id"]:
        await _not_yours(callback)
        return
    agreement = await trading.agree(stores, trade, callback.from_user.id)
    for encounter in agreement.fled:
        await announce_fled(callback.bot, encounter)
    if agreement.blocked is not None:
        await callback.answer(text(f"trade.{agreement.blocked}"), show_alert=True)
        return
    if agreement.trade is None:
        await _ended(callback)
        return
    await callback.answer()
    await _show_stage(callback, stores, agreement.trade)


@router.callback_query(PokemonListPage.filter(F.screen == TRADE_SCREEN))
async def page_turned(callback: CallbackQuery, callback_data: PokemonListPage, stores: Stores) -> None:
    if callback.from_user.id != callback_data.owner_id or not isinstance(callback.message, Message):
        await _not_yours(callback)
        return
    trade = await trading.current_of(stores, callback.from_user.id)
    if trade is None or rules.chooser_id(trade) != callback.from_user.id:
        await _ended(callback)
        return
    page = await trading.turn_chooser_page(
        stores,
        trade,
        callback_data.page,
        callback_data.delta,
        callback_data.anchor,
    )
    await callback.answer()
    if page is not None and page.page.pokemon:
        await _show(
            callback,
            trade_view.choose_text(trade, page),
            trade_pick_keyboard(callback.from_user.id, str(trade["_id"]), page.page),
        )


@router.callback_query(TradeAction.filter(F.action == "pick"))
async def pokemon_picked(callback: CallbackQuery, callback_data: TradeAction, stores: Stores) -> None:
    trade = await trading.get(stores, callback_data.trade_id)
    if trade is None or trade["state"] not in rules.CHOOSER_SIDE or not isinstance(callback.message, Message):
        await _ended(callback)
        return
    if callback.from_user.id != rules.chooser_id(trade):
        await _not_yours(callback)
        return
    choice = await trading.choose(stores, trade, callback.from_user.id, callback_data.value)
    if choice.hatched:
        await callback.answer(text("trade.hatched"), show_alert=True)
        return
    if choice.trade is None:
        await _ended(callback)
        return
    await callback.answer()
    await _show_stage(callback, stores, choice.trade)


@router.callback_query(TradeAction.filter(F.action == "accept"))
async def accept_pressed(callback: CallbackQuery, callback_data: TradeAction, stores: Stores) -> None:
    trade = await trading.get(stores, callback_data.trade_id)
    if trade is None or not isinstance(callback.message, Message):
        await _ended(callback)
        return
    if not rules.is_participant(trade, callback.from_user.id):
        await _not_yours(callback)
        return
    result = await trading.accept(stores, callback_data.trade_id, callback.from_user.id)
    if result.status == trading.ENDED:
        await _ended(callback)
    elif result.status == trading.ALREADY_ACCEPTED:
        await callback.answer(text("trade.already_accepted"))
    elif result.status == trading.WAITING:
        await callback.answer(text("trade.accepted"))
    else:
        await callback.answer()
        await _show(callback, trade_view.result_text(result.trade))


@router.callback_query(TradeAction.filter(F.action == "cancel"))
async def cancel_pressed(callback: CallbackQuery, callback_data: TradeAction, stores: Stores) -> None:
    trade = await trading.get(stores, callback_data.trade_id)
    if trade is None or not isinstance(callback.message, Message):
        await _ended(callback)
        return
    if not rules.is_participant(trade, callback.from_user.id):
        await _not_yours(callback)
        return
    closed = await trading.cancel(stores, callback_data.trade_id)
    if closed is None:
        await _ended(callback)
        return
    await callback.answer()
    await _show(callback, trade_view.result_text(closed))


async def _announce_result(bot: Bot, trade: dict) -> None:
    if trade.get("message_id") is None:
        return
    try:
        await bot.edit_message_text(
            trade_view.result_text(trade),
            chat_id=trade["chat_id"],
            message_id=trade["message_id"],
        )
    except TelegramAPIError:
        logger.info("Could not update trade message %s", trade["_id"])


async def finish_idle_trades(bot: Bot, stores: Stores) -> None:
    while True:
        try:
            while (trade := await trading.next_settled(stores)) is not None:
                await _announce_result(bot, trade)
        except Exception:
            logger.exception("Could not check idle trades")
        await asyncio.sleep(EXPIRY_CHECK_SECONDS)
