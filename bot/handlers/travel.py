from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from bot.handlers.journey import JourneyRequired
from bot.services import travel
from bot.storage.stores import Stores
from bot.ui.keyboards import TravelChoice, travel_keyboard
from bot.ui.texts import text

router = Router()
router.message.middleware(JourneyRequired())


def _menu_text(menu: travel.TravelMenu) -> str:
    lines = "\n".join(
        text("travel.region_line", number=number, region=region)
        for number, region in enumerate(menu.regions, start=1)
    )
    sections = [text("travel.ask"), lines]
    if menu.has_more:
        sections.append(text("travel.rank_up"))
    sections.append(text("travel.current", region=menu.current))
    return "\n\n".join(sections)


@router.message(Command("travel"), F.from_user)
async def travel_command(message: Message, stores: Stores) -> None:
    trainer_id = message.from_user.id
    menu = await travel.menu_of(stores, trainer_id)
    if menu is None:
        await message.reply(text("common.start_journey"))
        return
    if menu.in_safari:
        await message.reply(text("travel.in_safari"))
        return
    if menu.in_ev_training:
        await message.reply(text("travel.in_ev_training"))
        return
    await message.reply(_menu_text(menu), reply_markup=travel_keyboard(trainer_id, len(menu.regions)))


@router.callback_query(TravelChoice.filter())
async def region_pressed(callback: CallbackQuery, callback_data: TravelChoice, stores: Stores) -> None:
    trainer_id = callback.from_user.id
    if trainer_id != callback_data.owner_id or not isinstance(callback.message, Message):
        await callback.answer(text("common.not_your_buttons"), show_alert=True)
        return
    result = await travel.go(stores, trainer_id, callback_data.region)
    if result.status == travel.IN_SAFARI:
        await callback.answer(text("travel.in_safari"), show_alert=True)
    elif result.status == travel.IN_EV_TRAINING:
        await callback.answer(text("travel.in_ev_training"), show_alert=True)
    elif result.status == travel.ALREADY_HERE:
        await callback.answer(text("travel.already_here", region=result.region), show_alert=True)
    elif result.status == travel.TRAVELED:
        await callback.answer()
        await callback.message.edit_text(text("travel.traveled", region=result.region), reply_markup=None)
    else:
        await callback.answer(text("travel.locked"), show_alert=True)
