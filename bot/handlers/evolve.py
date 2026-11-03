from html import escape, unescape

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.types import CallbackQuery, Message, ReplyParameters

from bot.game import creatures, pokedex
from bot.handlers.pokemon_picker import pokemon_command
from bot.services import evolving
from bot.storage.stores import Stores
from bot.ui import battle_view
from bot.ui.keyboards import EvolveAction, evolve_keyboard
from bot.ui.texts import text

router = Router()

REFUSALS = {
    evolving.NEVER: "evolve.never",
    evolving.NOT_YET: "evolve.not_yet",
    evolving.IN_BATTLE: "hunt.already_in_battle",
    evolving.IN_TRADE: "trade.locked",
    evolving.GONE: "evolve.stale",
    evolving.FAILED: "evolve.failed",
}


def _refusal_text(status: str, pokemon: dict | None) -> str:
    name = escape(creatures.shown_name(pokemon)) if pokemon else ""
    return text(REFUSALS[status], name=name)


def _quote(quoted_id: int | None) -> ReplyParameters | None:
    return ReplyParameters(message_id=quoted_id, allow_sending_without_reply=True) if quoted_id else None


async def _cannot_evolve(pokemon: dict, trainer_id: int, stores: Stores) -> str | None:
    status = await evolving.status_of(stores, trainer_id, pokemon)
    return None if status == evolving.READY else _refusal_text(status, pokemon)


@pokemon_command("evolve", code="ev", refuse=_cannot_evolve)
async def ask_to_evolve(
    message: Message,
    owner_id: int,
    pokemon: dict,
    quoted_id: int | None,
    stores: Stores,
) -> None:
    await message.answer(
        text("evolve.confirm", name=escape(creatures.shown_name(pokemon)), level=pokemon["level"]),
        reply_parameters=_quote(quoted_id),
        reply_markup=evolve_keyboard(owner_id, str(pokemon["_id"]), pokemon["dex_id"]),
    )


async def _is_owner(callback: CallbackQuery, callback_data: EvolveAction) -> bool:
    if callback.from_user.id == callback_data.owner_id and isinstance(callback.message, Message):
        return True
    await callback.answer(text("common.not_your_buttons"), show_alert=True)
    return False


async def _delete(message: Message) -> None:
    try:
        await message.delete()
    except TelegramBadRequest:
        pass


@router.callback_query(EvolveAction.filter(F.action == "no"))
async def evolve_cancelled(callback: CallbackQuery, callback_data: EvolveAction) -> None:
    if not await _is_owner(callback, callback_data):
        return
    await callback.answer()
    await _delete(callback.message)


@router.callback_query(EvolveAction.filter(F.action == "yes"))
async def evolve_confirmed(callback: CallbackQuery, callback_data: EvolveAction, stores: Stores) -> None:
    if not await _is_owner(callback, callback_data):
        return
    result = await evolving.evolve(stores, callback.from_user.id, callback_data.pokemon_id, callback_data.dex_id)
    if result.status != evolving.EVOLVED:
        await callback.answer(unescape(_refusal_text(result.status, result.pokemon)), show_alert=True)
        return
    await callback.answer()
    message = callback.message
    caption = text(
        "evolve.evolved",
        name=escape(creatures.shown_name(result.pokemon)),
        new_name=pokedex.species_name(result.new_dex_id),
    )
    quoted = message.reply_to_message.message_id if message.reply_to_message else None
    try:
        await message.answer_photo(
            battle_view.artwork(result.new_dex_id, result.pokemon.get("shiny", False)),
            caption=caption,
            reply_parameters=_quote(quoted),
        )
    except TelegramAPIError:
        await message.answer(caption, reply_parameters=_quote(quoted))
    await _delete(message)
