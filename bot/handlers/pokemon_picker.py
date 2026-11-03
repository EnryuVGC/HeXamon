from dataclasses import dataclass
from html import escape, unescape
from typing import Awaitable, Callable

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, Message

from bot.game.name_search import parse_list_screen
from bot.handlers.journey import JourneyRequired
from bot.handlers.private import private_only
from bot.services import pokemon_search
from bot.storage.stores import Stores
from bot.ui import pokemon_picker as picker_view
from bot.ui.pokemon_list import PokemonListPage
from bot.ui.pokemon_picker import PokemonPick, PokemonSuggestion
from bot.ui.texts import text

router = Router()
router.message.middleware(JourneyRequired())

START_COMMAND = "start"

PokemonChosen = Callable[[Message, int, dict, int | None, Stores], Awaitable[None]]
PokemonRefusal = Callable[[dict, int, Stores], Awaitable[str | None]]


@dataclass(frozen=True)
class PokemonCommand:
    name: str
    code: str
    on_chosen: PokemonChosen
    refuse: PokemonRefusal | None = None
    refusal_alert: bool = False

    async def refusal(self, pokemon: dict, trainer_id: int, stores: Stores) -> str | None:
        return await self.refuse(pokemon, trainer_id, stores) if self.refuse else None


_commands: dict[str, PokemonCommand] = {}


def pokemon_command(
    name: str,
    code: str,
    refuse: PokemonRefusal | None = None,
    refusal_alert: bool = False,
    private: bool = False,
) -> Callable[[PokemonChosen], PokemonChosen]:
    def decorator(on_chosen: PokemonChosen) -> PokemonChosen:
        spec = PokemonCommand(name, code, on_chosen, refuse, refusal_alert)
        _commands[code] = spec

        async def command_handler(message: Message, command: CommandObject, stores: Stores) -> None:
            query = None if command.command == START_COMMAND else command.args
            await _run_command(spec, message, query, stores)

        handler = private_only(name)(command_handler) if private else command_handler
        router.message.register(handler, Command(name), F.from_user)
        return on_chosen

    return decorator


async def _is_owner(callback: CallbackQuery, owner_id: int) -> bool:
    if callback.from_user.id == owner_id and isinstance(callback.message, Message):
        return True
    await callback.answer(text("common.not_your_buttons"), show_alert=True)
    return False


async def _gone(callback: CallbackQuery) -> None:
    await callback.answer(text("pokemon_picker.gone"), show_alert=True)


def _command_id(prompt: Message) -> int | None:
    return prompt.reply_to_message.message_id if prompt.reply_to_message else None


async def _delete(message: Message) -> None:
    try:
        await message.delete()
    except TelegramBadRequest:
        pass


async def _show_list(message: Message, body: str, markup) -> None:
    try:
        await message.edit_text(body, reply_markup=markup)
    except TelegramBadRequest as error:
        if "message is not modified" not in str(error):
            raise


async def _run_command(spec: PokemonCommand, message: Message, query: str | None, stores: Stores) -> None:
    trainer_id = message.from_user.id
    if not query:
        await message.reply(text("pokemon_picker.usage", command=spec.name))
        return
    result = await pokemon_search.search(stores, trainer_id, query)
    if result is None:
        await message.reply(text("pokemon_picker.not_found"))
    elif isinstance(result, pokemon_search.Suggestion):
        await message.reply(
            text("pokemon_picker.did_you_mean", name=escape(result.name)),
            reply_markup=picker_view.suggestion_keyboard(trainer_id, spec.code, result.kind, result.example_id),
        )
    elif result.pokemon is not None:
        refusal = await spec.refusal(result.pokemon, trainer_id, stores)
        if refusal:
            await message.reply(refusal)
            return
        await spec.on_chosen(message, trainer_id, result.pokemon, message.message_id, stores)
    else:
        await message.reply(
            picker_view.list_text(spec.name, result.page),
            reply_markup=picker_view.list_keyboard(trainer_id, spec.code, result.kind, result.page),
        )


@router.callback_query(PokemonSuggestion.filter())
async def suggestion_answered(callback: CallbackQuery, callback_data: PokemonSuggestion, stores: Stores) -> None:
    if not await _is_owner(callback, callback_data.owner_id):
        return
    if not callback_data.accepted:
        await callback.answer()
        await _delete(callback.message)
        return
    spec = _commands.get(callback_data.command_code)
    trainer_id = callback.from_user.id
    found = await pokemon_search.accept_suggestion(stores, trainer_id, callback_data.kind, callback_data.example_id)
    if spec is None or found is None:
        await _gone(callback)
        return
    if found.pokemon is not None:
        refusal = await spec.refusal(found.pokemon, trainer_id, stores)
        if refusal:
            await callback.answer(unescape(refusal), show_alert=spec.refusal_alert)
            return
    await callback.answer()
    if found.pokemon is not None:
        await spec.on_chosen(callback.message, trainer_id, found.pokemon, _command_id(callback.message), stores)
        await _delete(callback.message)
        return
    await _show_list(
        callback.message,
        picker_view.list_text(spec.name, found.page),
        picker_view.list_keyboard(trainer_id, spec.code, found.kind, found.page),
    )


@router.callback_query(PokemonListPage.filter(F.screen.func(parse_list_screen)))
async def list_page_turned(callback: CallbackQuery, callback_data: PokemonListPage, stores: Stores) -> None:
    if not await _is_owner(callback, callback_data.owner_id):
        return
    kind, command_code = parse_list_screen(callback_data.screen)
    spec = _commands.get(command_code)
    trainer_id = callback.from_user.id
    page = await pokemon_search.turn_list_page(
        stores,
        trainer_id,
        kind,
        callback_data.page,
        callback_data.delta,
        callback_data.anchor,
    )
    await callback.answer()
    if spec is not None and page is not None and page.pokemon:
        await _show_list(
            callback.message,
            picker_view.list_text(spec.name, page),
            picker_view.list_keyboard(trainer_id, spec.code, kind, page),
        )


@router.callback_query(PokemonPick.filter())
async def pokemon_picked(callback: CallbackQuery, callback_data: PokemonPick, stores: Stores) -> None:
    if not await _is_owner(callback, callback_data.owner_id):
        return
    spec = _commands.get(callback_data.command_code)
    trainer_id = callback.from_user.id
    pokemon = await pokemon_search.pokemon_of(stores, trainer_id, callback_data.pokemon_id)
    if spec is None or pokemon is None:
        await _gone(callback)
        return
    refusal = await spec.refusal(pokemon, trainer_id, stores)
    if refusal:
        await callback.answer(unescape(refusal), show_alert=spec.refusal_alert)
        return
    await callback.answer()
    await spec.on_chosen(callback.message, trainer_id, pokemon, _command_id(callback.message), stores)
    await _delete(callback.message)
