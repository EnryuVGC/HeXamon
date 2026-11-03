from html import escape

from aiogram import F, Router
from aiogram.dispatcher.event.bases import SkipHandler
from aiogram.types import CallbackQuery, Message, ReplyParameters

from bot.game.nicknames import MAX_NICKNAME_LENGTH
from bot.game.pokedex import species_name
from bot.handlers.pokemon_picker import pokemon_command
from bot.services import nicknames
from bot.storage.stores import Stores
from bot.ui.keyboards import NicknameChoice, nickname_reply_prompt
from bot.ui.texts import text

router = Router()


@router.callback_query(NicknameChoice.filter())
async def nickname_button(
    callback: CallbackQuery,
    callback_data: NicknameChoice,
    stores: Stores,
) -> None:
    if callback.from_user.id != callback_data.owner_id:
        await callback.answer(text("common.not_your_buttons"), show_alert=True)
        return
    if await nicknames.in_trade(stores, callback.from_user.id):
        await callback.answer(text("trade.locked"), show_alert=True)
        return

    pokemon = await nicknames.pokemon_to_name(stores, callback.from_user.id, callback_data.pokemon_id)
    if pokemon is None or not isinstance(callback.message, Message):
        await callback.answer(text("hunt.already_named"), show_alert=True)
        return

    await callback.answer()
    prompt = await callback.message.answer(
        text("start.nickname_prompt", name=species_name(pokemon["dex_id"])),
        reply_parameters=ReplyParameters(
            message_id=callback.message.message_id,
            allow_sending_without_reply=True,
        ),
        reply_markup=nickname_reply_prompt(),
    )
    await nicknames.remember_prompt(
        stores,
        callback.from_user.id,
        callback_data.pokemon_id,
        prompt.chat.id,
        prompt.message_id,
    )


@pokemon_command("nickname", code="nk")
async def ask_for_nickname(
    message: Message,
    owner_id: int,
    pokemon: dict,
    quoted_id: int | None,
    stores: Stores,
) -> None:
    if await nicknames.in_trade(stores, owner_id):
        await message.answer(text("trade.locked"))
        return
    prompt = await message.answer(
        text("start.nickname_prompt", name=species_name(pokemon["dex_id"])),
        reply_parameters=(
            ReplyParameters(message_id=quoted_id, allow_sending_without_reply=True) if quoted_id else None
        ),
        reply_markup=nickname_reply_prompt(selective=quoted_id is not None),
    )
    await nicknames.remember_prompt(stores, owner_id, str(pokemon["_id"]), prompt.chat.id, prompt.message_id)


@router.message(F.from_user, F.reply_to_message, F.text, ~F.text.startswith("/"))
async def nickname_reply(message: Message, stores: Stores) -> None:
    trainer_id = message.from_user.id
    prompt_id = message.reply_to_message.message_id
    pokemon_id = await nicknames.prompt_target(stores, trainer_id, message.chat.id, prompt_id)
    if pokemon_id is None:
        raise SkipHandler

    nickname = nicknames.validate(message.text)
    if nickname is None:
        await message.reply(text("start.nickname_invalid", max_length=MAX_NICKNAME_LENGTH))
        return

    name = await nicknames.save(stores, trainer_id, message.chat.id, prompt_id, pokemon_id, nickname)
    if name is None:
        raise SkipHandler
    await message.reply(text("start.nickname_saved", name=name, nickname=escape(nickname)))
