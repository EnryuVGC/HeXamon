from html import escape

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message, ReplyParameters

from bot.game import creatures
from bot.handlers.hunt import announce_fled
from bot.handlers.pokemon_picker import pokemon_command
from bot.services import release
from bot.storage.stores import Stores
from bot.ui.keyboards import ReleaseAction, caught_keyboard, release_keyboard
from bot.ui.texts import text

router = Router()


async def _is_owner(callback: CallbackQuery, callback_data: ReleaseAction) -> bool:
    if callback.from_user.id == callback_data.owner_id and isinstance(callback.message, Message):
        return True
    await callback.answer(text("common.not_your_buttons"), show_alert=True)
    return False


async def _gone(callback: CallbackQuery) -> None:
    await callback.answer(text("pokemon_picker.gone"), show_alert=True)
    await callback.message.edit_reply_markup(reply_markup=None)


def _confirm_text(pokemon: dict) -> str:
    return text(
        "release.confirm",
        level=pokemon["level"],
        name=escape(creatures.shown_name(pokemon)),
        nature=pokemon["nature"],
        ivs=sum(pokemon["ivs"]),
        evs=sum(creatures.evs_of(pokemon)),
    )


async def _refusal(pokemon: dict, trainer_id: int, stores: Stores) -> str | None:
    if pokemon.get("egg"):
        return text("release.hatched")
    return None if await release.can_lose_one(stores, trainer_id) else text("release.last_pokemon")


@pokemon_command("release", code="rl", refuse=_refusal, refusal_alert=True)
async def ask_to_release(
    message: Message,
    owner_id: int,
    pokemon: dict,
    quoted_id: int | None,
    stores: Stores,
) -> None:
    await message.answer(
        _confirm_text(pokemon),
        reply_parameters=(
            ReplyParameters(message_id=quoted_id, allow_sending_without_reply=True) if quoted_id else None
        ),
        reply_markup=release_keyboard(owner_id, str(pokemon["_id"])),
    )


@router.callback_query(ReleaseAction.filter(F.action == "ask"))
async def release_pressed(callback: CallbackQuery, callback_data: ReleaseAction, stores: Stores) -> None:
    if not await _is_owner(callback, callback_data):
        return
    trainer_id = callback.from_user.id
    pokemon = await release.pokemon_to_release(stores, trainer_id, callback_data.pokemon_id)
    if pokemon is None:
        await _gone(callback)
        return
    refusal = await _refusal(pokemon, trainer_id, stores)
    if refusal:
        await callback.answer(refusal, show_alert=True)
        return

    await release.ask(
        stores,
        trainer_id,
        callback_data.pokemon_id,
        callback.message.message_id,
        callback.message.html_text,
    )
    await callback.answer()
    await callback.message.edit_text(
        _confirm_text(pokemon),
        reply_markup=release_keyboard(trainer_id, callback_data.pokemon_id),
    )


@router.callback_query(ReleaseAction.filter(F.action == "no"))
async def release_declined(callback: CallbackQuery, callback_data: ReleaseAction, stores: Stores) -> None:
    if not await _is_owner(callback, callback_data):
        return
    trainer_id = callback.from_user.id
    pokemon = await release.pokemon_to_release(stores, trainer_id, callback_data.pokemon_id)
    if pokemon is None:
        await _gone(callback)
        return

    body = await release.previous_body(stores, trainer_id, callback_data.pokemon_id, callback.message.message_id)
    await callback.answer()
    if body is None:
        await callback.message.edit_text(
            text("release.stayed", name=escape(creatures.shown_name(pokemon))),
            reply_markup=None,
        )
        return
    await callback.message.edit_text(
        body,
        reply_markup=caught_keyboard(trainer_id, callback_data.pokemon_id, pokemon["dex_id"]),
    )


@router.callback_query(ReleaseAction.filter(F.action == "yes"))
async def release_confirmed(callback: CallbackQuery, callback_data: ReleaseAction, stores: Stores) -> None:
    if not await _is_owner(callback, callback_data):
        return
    result = await release.release(
        stores,
        callback.from_user.id,
        callback_data.pokemon_id,
        callback.message.message_id,
    )
    if result.fled is not None:
        await announce_fled(callback.bot, result.fled)
    if result.status == release.GONE:
        await _gone(callback)
    elif result.status == release.HATCHED:
        await callback.answer(text("release.hatched"), show_alert=True)
    elif result.status == release.IN_BATTLE:
        await callback.answer(text("release.in_battle"), show_alert=True)
    elif result.status == release.IN_TRADE:
        await callback.answer(text("trade.locked"), show_alert=True)
    elif result.status == release.LAST_POKEMON:
        await callback.answer(text("release.last_pokemon"), show_alert=True)
    else:
        await callback.answer()
        name = escape(creatures.shown_name(result.pokemon))
        await callback.message.edit_text(text("release.released", name=name), reply_markup=None)
