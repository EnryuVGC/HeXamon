from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from bot.game.trainer_stats import NATIONAL_DEX_SIZE
from bot.handlers.journey import JourneyRequired
from bot.services import trainer_card
from bot.services.trainer_stats import TrainerStats, stats_of
from bot.storage.stores import Stores
from bot.ui.keyboards import MoreStats, more_stats_keyboard
from bot.ui.texts import text

router = Router()
router.message.middleware(JourneyRequired())

CARD_FILENAME = "trainer_card.png"


def _more_stats_text(stats: TrainerStats) -> str:
    return text(
        "mystats.more",
        ratio=f"{stats.win_ratio:.2f}",
        balls=stats.balls_used,
        caught=stats.total_caught,
        rate=f"{stats.catch_rate:.2f}",
        seen=stats.seen,
        obtained=stats.obtained,
        total=NATIONAL_DEX_SIZE,
    )


@router.message(Command("mystats"), F.from_user)
async def mystats_command(message: Message, stores: Stores) -> None:
    trainer_id = message.from_user.id
    stats = await stats_of(stores, trainer_id)
    if stats is None:
        await message.reply(text("common.start_journey"))
        return
    card = await trainer_card.card_image(stores, trainer_id)
    await message.reply_photo(
        BufferedInputFile(card, filename=CARD_FILENAME),
        reply_markup=more_stats_keyboard(trainer_id),
    )


@router.callback_query(MoreStats.filter())
async def more_stats_pressed(callback: CallbackQuery, callback_data: MoreStats, stores: Stores) -> None:
    trainer_id = callback.from_user.id
    if trainer_id != callback_data.owner_id or not isinstance(callback.message, Message):
        await callback.answer(text("common.not_your_buttons"), show_alert=True)
        return
    await callback.answer()
    stats = await stats_of(stores, trainer_id)
    if stats is None:
        return
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except TelegramBadRequest:
        return
    await callback.message.reply(_more_stats_text(stats))
