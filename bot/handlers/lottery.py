import asyncio
import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from bot.game import lottery as rules
from bot.handlers.journey import JourneyRequired
from bot.handlers.private import private_only
from bot.services import lottery
from bot.storage.stores import Stores
from bot.ui import lottery_view
from bot.ui.keyboards import (
    LOTTERY_CLEAR,
    LOTTERY_COUNTDOWN,
    LOTTERY_ENTRIES,
    LOTTERY_MULTIPLIER,
    LOTTERY_NUMBER,
    LOTTERY_PLAY,
    LOTTERY_RANDOM,
    LOTTERY_SAVE,
    LotteryAction,
    lottery_menu_keyboard,
    lottery_picker_keyboard,
    lottery_saved_keyboard,
)
from bot.ui.texts import text

logger = logging.getLogger(__name__)

DRAW_CHECK_SECONDS = 30
REFUSALS = {
    lottery.NO_MONEY: "lottery.no_money",
    lottery.MAX_REACHED: "lottery.max_reached",
    lottery.DUPLICATE: "lottery.duplicate",
    lottery.DRAWING: "lottery.drawing",
}

router = Router()
router.message.middleware(JourneyRequired())


async def _show(callback: CallbackQuery, body: str, keyboard: InlineKeyboardMarkup | None = None) -> None:
    if not isinstance(callback.message, Message):
        return
    try:
        await callback.message.edit_text(body, reply_markup=keyboard)
    except TelegramBadRequest as error:
        if "message is not modified" not in str(error):
            raise


async def _show_picker(callback: CallbackQuery, picks: list[int], multiplied: bool) -> None:
    await _show(callback, lottery_view.picker_text(picks, multiplied), lottery_picker_keyboard(picks, multiplied))
    await callback.answer()


@router.message(Command("lottery"), F.from_user)
@private_only("lottery")
async def lottery_command(message: Message, stores: Stores) -> None:
    current = await lottery.overview(stores, message.from_user.id)
    await message.reply(
        lottery_view.menu_text(current.jackpot),
        reply_markup=lottery_menu_keyboard(bool(current.tickets)),
    )


@router.message(Command("lotteryinfo"), F.from_user)
@private_only("lotteryinfo")
async def lottery_info_command(message: Message) -> None:
    await message.reply(lottery_view.info_text())


@router.message(Command("lastlottery"), F.from_user)
@private_only("lastlottery")
async def last_lottery_command(message: Message, stores: Stores) -> None:
    last = await lottery.last_draw(stores, message.from_user.id)
    if last is None:
        await message.reply(text("lottery.no_draws"))
        return
    await message.reply(lottery_view.last_text(last.draw, last.tickets))


@router.callback_query(LotteryAction.filter(F.action == LOTTERY_COUNTDOWN))
async def lottery_countdown(callback: CallbackQuery) -> None:
    await callback.answer(lottery_view.countdown_text(lottery.seconds_until_draw()), show_alert=True)


@router.callback_query(LotteryAction.filter(F.action == LOTTERY_PLAY))
async def lottery_play(callback: CallbackQuery, stores: Stores) -> None:
    current = await lottery.overview(stores, callback.from_user.id)
    if len(current.tickets) >= rules.MAX_ENTRIES:
        await callback.answer(text("lottery.max_reached"), show_alert=True)
        return
    await _show_picker(callback, [], False)


@router.callback_query(LotteryAction.filter(F.action == LOTTERY_NUMBER))
async def lottery_number(callback: CallbackQuery, callback_data: LotteryAction) -> None:
    picks = rules.toggle_pick(rules.decode_picks(callback_data.picks), callback_data.number)
    if picks is None:
        await callback.answer(text("lottery.too_many", count=rules.NUMBER_COUNT), show_alert=True)
        return
    await _show_picker(callback, picks, callback_data.multiplied)


@router.callback_query(LotteryAction.filter(F.action == LOTTERY_MULTIPLIER))
async def lottery_multiplier(callback: CallbackQuery, callback_data: LotteryAction) -> None:
    await _show_picker(callback, rules.decode_picks(callback_data.picks), not callback_data.multiplied)


@router.callback_query(LotteryAction.filter(F.action == LOTTERY_RANDOM))
async def lottery_random(callback: CallbackQuery, callback_data: LotteryAction) -> None:
    await _show_picker(callback, rules.roll_numbers(), callback_data.multiplied)


@router.callback_query(LotteryAction.filter(F.action == LOTTERY_CLEAR))
async def lottery_clear(callback: CallbackQuery, callback_data: LotteryAction) -> None:
    await _show_picker(callback, [], callback_data.multiplied)


@router.callback_query(LotteryAction.filter(F.action == LOTTERY_SAVE))
async def lottery_save(callback: CallbackQuery, callback_data: LotteryAction, stores: Stores) -> None:
    picks = rules.decode_picks(callback_data.picks)
    if not rules.is_complete(picks):
        await callback.answer(text("lottery.pick_all", count=rules.NUMBER_COUNT), show_alert=True)
        return
    status = await lottery.save_entry(stores, callback.from_user.id, picks, callback_data.multiplied)
    if status != lottery.SAVED:
        cost = rules.entry_cost(callback_data.multiplied)
        await callback.answer(text(REFUSALS[status], cost=cost), show_alert=True)
        return
    await _show(callback, lottery_view.saved_text(picks, callback_data.multiplied), lottery_saved_keyboard())
    await callback.answer()


@router.callback_query(LotteryAction.filter(F.action == LOTTERY_ENTRIES))
async def lottery_entries(callback: CallbackQuery, stores: Stores) -> None:
    current = await lottery.overview(stores, callback.from_user.id)
    await _show(callback, lottery_view.entries_text(current.jackpot, current.tickets))
    await callback.answer()


async def _announce(bot: Bot, winnings: lottery.Winnings) -> None:
    body = lottery_view.winnings_text(
        winnings.day,
        winnings.numbers,
        winnings.counters,
        winnings.key_items,
        winnings.money_limited,
    )
    try:
        await bot.send_message(winnings.trainer_id, body)
    except TelegramAPIError:
        pass


async def run_draws(bot: Bot, stores: Stores) -> None:
    while True:
        try:
            while (winnings := await lottery.next_winnings(stores)) is not None:
                await _announce(bot, winnings)
        except Exception:
            logger.exception("Could not run the lottery draw")
        await asyncio.sleep(DRAW_CHECK_SECONDS)
