from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.filters import CommandObject, CommandStart
from aiogram.types import CallbackQuery, Message, ReplyParameters

from bot.handlers.private import private_only
from bot.services import nicknames, onboarding, referrals, reply_keyboard
from bot.storage.stores import Stores
from bot.ui import referrals_view
from bot.ui.keyboards import (
    FirstPartnerChoice,
    FirstPartnerNone,
    fallback_partner_keyboard,
    first_partner_keyboard,
    main_keyboard,
    nickname_reply_prompt,
)
from bot.ui.texts import text

router = Router()


def _reply_to_original(message: Message) -> ReplyParameters | None:
    original = message.reply_to_message
    if original is None:
        return None
    return ReplyParameters(message_id=original.message_id, allow_sending_without_reply=True)


async def _remove_welcome(message: Message) -> None:
    try:
        await message.delete()
    except TelegramBadRequest:
        await message.edit_reply_markup(reply_markup=None)


async def _tell_referrer(message: Message, referrer_id: int, name: str) -> None:
    try:
        await message.bot.send_message(referrer_id, referrals_view.joined_text(name))
    except TelegramAPIError:
        pass


@router.message(CommandStart(), F.from_user)
@private_only("start")
async def start_command(message: Message, stores: Stores, command: CommandObject) -> None:
    trainer_id = message.from_user.id
    if await onboarding.needs_first_partner(stores, trainer_id):
        await message.reply(
            text("start.welcome"),
            reply_markup=first_partner_keyboard(trainer_id, onboarding.available_partners()),
        )
        name = message.from_user.full_name
        referrer_id = await referrals.use_link(stores, trainer_id, name, command.args)
        if referrer_id is not None:
            await _tell_referrer(message, referrer_id, name)
    else:
        await reply_keyboard.mark_open(stores, trainer_id)
        await message.reply(text("start.already_started"), reply_markup=main_keyboard())


@router.callback_query(FirstPartnerNone.filter())
async def first_partner_none(callback: CallbackQuery, callback_data: FirstPartnerNone) -> None:
    trainer_id = callback.from_user.id
    if trainer_id != callback_data.owner_id:
        await callback.answer(text("common.not_your_buttons"), show_alert=True)
        return

    await callback.answer()
    if not isinstance(callback.message, Message):
        return

    if callback_data.confirming:
        partner = onboarding.fallback_partner()
        body = text("start.none_confirm", name=partner.name)
        markup = fallback_partner_keyboard(trainer_id, partner)
    else:
        body = text("start.welcome")
        markup = first_partner_keyboard(trainer_id, onboarding.available_partners())
    try:
        await callback.message.edit_text(body, reply_markup=markup)
    except TelegramBadRequest as error:
        if "message is not modified" not in str(error):
            raise


@router.callback_query(FirstPartnerChoice.filter())
async def first_partner_chosen(
    callback: CallbackQuery,
    callback_data: FirstPartnerChoice,
    stores: Stores,
) -> None:
    if callback.from_user.id != callback_data.owner_id:
        await callback.answer(text("common.not_your_buttons"), show_alert=True)
        return

    trainer_id = callback.from_user.id
    chosen = await onboarding.choose_first_partner(stores, trainer_id, callback_data.dex_id)
    if chosen is None:
        await callback.answer(text("start.already_chosen"), show_alert=True)
    else:
        await callback.answer()

    if not isinstance(callback.message, Message):
        return

    await _remove_welcome(callback.message)
    if chosen is None:
        return

    partner, pokemon_id = chosen
    reply_parameters = _reply_to_original(callback.message)
    chosen_text = "start.none_chosen" if partner == onboarding.fallback_partner() else "start.partner_chosen"
    await reply_keyboard.mark_open(stores, trainer_id)
    await callback.message.answer(
        text(chosen_text, name=partner.name),
        reply_parameters=reply_parameters,
        reply_markup=main_keyboard(),
    )
    prompt = await callback.message.answer(
        text("start.nickname_prompt", name=partner.name),
        reply_parameters=reply_parameters,
        reply_markup=nickname_reply_prompt(),
    )
    await nicknames.remember_prompt(stores, trainer_id, pokemon_id, prompt.chat.id, prompt.message_id)
