from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandObject
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardMarkup, InputMediaPhoto, Message

from bot.game import card_styles as rules
from bot.handlers.journey import JourneyRequired
from bot.handlers.private import private_only
from bot.services import trainer_card
from bot.storage.stores import Stores
from bot.ui.keyboards import CardAction, card_main_keyboard, card_options_keyboard, card_template_keyboard, card_text_keyboard
from bot.ui.texts import text

router = Router()
router.message.middleware(JourneyRequired())

CARD_FILENAME = "trainer_card.png"


def _photo(image: bytes) -> BufferedInputFile:
    return BufferedInputFile(image, filename=CARD_FILENAME)


@router.message(Command("card"), F.from_user)
@private_only("card")
async def card_command(message: Message, stores: Stores) -> None:
    trainer_id = message.from_user.id
    image = await trainer_card.card_image(stores, trainer_id)
    if image is None:
        await message.reply(text("common.start_journey"))
        return
    await message.reply_photo(_photo(image), caption=text("card.main"), reply_markup=card_main_keyboard(trainer_id))


@router.message(Command("setcolor"), F.from_user)
@private_only("setcolor")
async def setcolor_command(message: Message, command: CommandObject, stores: Stores) -> None:
    color = rules.custom_color(command.args)
    if color is None:
        await message.reply(text("card.setcolor_usage"))
        return
    await trainer_card.save_custom_color(stores, message.from_user.id, color)
    await message.reply(text("card.setcolor_saved", color=color))


async def _show(callback: CallbackQuery, image: bytes, caption: str, markup: InlineKeyboardMarkup) -> None:
    try:
        await callback.message.edit_media(InputMediaPhoto(media=_photo(image), caption=caption), reply_markup=markup)
    except TelegramBadRequest as error:
        if "message is not modified" not in str(error):
            raise


async def _show_main(callback: CallbackQuery, stores: Stores, trainer_id: int) -> None:
    image = await trainer_card.card_image(stores, trainer_id)
    if image is not None:
        await _show(callback, image, text("card.main"), card_main_keyboard(trainer_id))


async def _show_options(callback: CallbackQuery, stores: Stores, trainer_id: int, field: str, value: int | None) -> None:
    style = await trainer_card.saved_style(stores, trainer_id)
    if style is None:
        return
    if field == rules.TEMPLATE:
        image = await trainer_card.template_grid()
        await _show(callback, image, text("card.choose_template", current=style.template), card_template_keyboard(trainer_id))
        return
    if field == rules.TEXT:
        image = await trainer_card.card_image(stores, trainer_id)
        if image is not None:
            await _show(callback, image, text("card.choose_text"), card_text_keyboard(trainer_id))
        return
    chosen = value if value is not None else rules.choice_of(style, field)
    preview = rules.with_choice(style, field, chosen)
    image = await trainer_card.card_image(stores, trainer_id, preview)
    if image is not None:
        await _show(callback, image, text(f"card.choose_{field}"), card_options_keyboard(trainer_id, field, chosen))


@router.callback_query(CardAction.filter())
async def card_pressed(callback: CallbackQuery, callback_data: CardAction, stores: Stores) -> None:
    trainer_id = callback.from_user.id
    if trainer_id != callback_data.owner_id or not isinstance(callback.message, Message):
        await callback.answer(text("common.not_your_buttons"), show_alert=True)
        return
    action, field, value = callback_data.action, callback_data.field, callback_data.value
    try:
        if action == "open":
            await _show_options(callback, stores, trainer_id, field, None)
        elif action == "pick" and rules.valid(field, value):
            await _show_options(callback, stores, trainer_id, field, value)
        elif action == "save":
            await trainer_card.save_choice(stores, trainer_id, field, value)
            await _show_main(callback, stores, trainer_id)
        elif action == "back":
            await _show_main(callback, stores, trainer_id)
    finally:
        await callback.answer()
