from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware, Bot, F, Router
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from aiogram.utils.deep_linking import create_start_link

from bot.handlers.journey import JourneyRequired
from bot.handlers.private import private_only
from bot.services import teams
from bot.storage.stores import Stores
from bot.ui import team_view
from bot.ui.keyboards import (
    TEAM_ADD_SCREEN,
    TeamAction,
    add_keyboard,
    editor_keyboard,
    order_keyboard,
    remove_keyboard,
    replace_keyboard,
    team_keyboard,
)
from bot.ui.pokemon_list import PokemonListPage
from bot.ui.texts import text


class TeamLockedInBattle(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[CallbackQuery, dict[str, Any]], Awaitable[Any]],
        event: CallbackQuery,
        data: dict[str, Any],
    ) -> Any:
        is_owner = event.from_user.id == data["callback_data"].owner_id
        if is_owner and await teams.in_battle(data["stores"], event.from_user.id):
            await event.answer(text("team.locked_in_battle"), show_alert=True)
            return None
        if is_owner and await teams.in_trade(data["stores"], event.from_user.id):
            await event.answer(text("trade.locked"), show_alert=True)
            return None
        return await handler(event, data)


router = Router()
router.message.middleware(JourneyRequired())
router.callback_query.middleware(TeamLockedInBattle())

EDITOR_LINK_COMMAND = "myteam_edit"


async def _team_markup(bot: Bot, message: Message, owner_id: int) -> InlineKeyboardMarkup:
    if message.chat.type == ChatType.PRIVATE:
        return team_keyboard(owner_id)
    return team_keyboard(owner_id, await create_start_link(bot, EDITOR_LINK_COMMAND))


async def _is_owner(callback: CallbackQuery, owner_id: int) -> bool:
    if callback.from_user.id == owner_id and isinstance(callback.message, Message):
        return True
    await callback.answer(text("common.not_your_buttons"), show_alert=True)
    return False


async def _show(callback: CallbackQuery, body: str, markup: InlineKeyboardMarkup) -> None:
    try:
        await callback.message.edit_text(body, reply_markup=markup)
    except TelegramBadRequest as error:
        if "message is not modified" not in str(error):
            raise


async def _needs_partner(callback: CallbackQuery) -> None:
    await callback.answer(text("common.start_journey"), show_alert=True)


async def _show_editor(callback: CallbackQuery, stores: Stores) -> None:
    team = await teams.active_team(stores, callback.from_user.id)
    if team is None:
        await _needs_partner(callback)
        return
    await _show(callback, team_view.editor_text(team.members, team.display), editor_keyboard(callback.from_user.id))


async def _show_add_page(callback: CallbackQuery, page) -> None:
    body = team_view.add_text(page.pokemon, page.display, page.team_full)
    await _show(callback, body, add_keyboard(callback.from_user.id, page))


async def _show_order(callback: CallbackQuery, team, chosen: int | None = None) -> None:
    keyboard = order_keyboard(callback.from_user.id, len(team.members), chosen)
    await _show(callback, team_view.order_text(team.members, team.display), keyboard)


@router.message(Command("myteam"), F.from_user)
async def myteam_command(message: Message, stores: Stores) -> None:
    trainer_id = message.from_user.id
    team = await teams.active_team(stores, trainer_id)
    if team is None:
        await message.reply(text("common.start_journey"))
        return
    await message.reply(
        team_view.team_text(team.number, team.members, team.display),
        reply_markup=await _team_markup(message.bot, message, trainer_id),
    )


@private_only(EDITOR_LINK_COMMAND)
async def editor_opened_from_link(message: Message, stores: Stores) -> None:
    trainer_id = message.from_user.id
    team = await teams.active_team(stores, trainer_id)
    if team is None:
        await message.reply(text("common.start_journey"))
        return
    await message.reply(team_view.editor_text(team.members, team.display), reply_markup=editor_keyboard(trainer_id))


@router.callback_query(TeamAction.filter(F.action == "view"))
async def team_pressed(callback: CallbackQuery, callback_data: TeamAction, stores: Stores) -> None:
    if not await _is_owner(callback, callback_data.owner_id):
        return
    team = await teams.select_team(stores, callback.from_user.id, int(callback_data.value))
    if team is None:
        await _needs_partner(callback)
        return
    await callback.answer()
    markup = await _team_markup(callback.bot, callback.message, callback.from_user.id)
    await _show(callback, team_view.team_text(team.number, team.members, team.display), markup)


@router.callback_query(TeamAction.filter(F.action == "edit"))
async def edit_pressed(callback: CallbackQuery, callback_data: TeamAction, stores: Stores) -> None:
    if not await _is_owner(callback, callback_data.owner_id):
        return
    await callback.answer()
    await _show_editor(callback, stores)


@router.callback_query(TeamAction.filter(F.action == "add"))
async def add_pressed(callback: CallbackQuery, callback_data: TeamAction, stores: Stores) -> None:
    if not await _is_owner(callback, callback_data.owner_id):
        return
    page = await teams.first_add_page(stores, callback.from_user.id)
    if page is None:
        await _needs_partner(callback)
        return
    if not page.pokemon:
        await callback.answer(text("team.no_pokemon_to_add"), show_alert=True)
        return
    await callback.answer()
    await _show_add_page(callback, page)


@router.callback_query(PokemonListPage.filter(F.screen == TEAM_ADD_SCREEN))
async def add_page_turned(callback: CallbackQuery, callback_data: PokemonListPage, stores: Stores) -> None:
    if not await _is_owner(callback, callback_data.owner_id):
        return
    page = await teams.turn_add_page(
        stores,
        callback.from_user.id,
        callback_data.page,
        callback_data.delta,
        callback_data.anchor,
    )
    await callback.answer()
    if page is not None and page.pokemon:
        await _show_add_page(callback, page)


@router.callback_query(TeamAction.filter(F.action == "pick"))
async def pokemon_picked(callback: CallbackQuery, callback_data: TeamAction, stores: Stores) -> None:
    if not await _is_owner(callback, callback_data.owner_id):
        return
    prompt = await teams.replace_prompt(stores, callback.from_user.id, callback_data.value)
    if prompt is not None:
        await callback.answer()
        team = prompt.team
        keyboard = replace_keyboard(callback.from_user.id, callback_data.value, len(team.member_ids))
        await _show(callback, team_view.replace_text(prompt.incoming, team.members, team.display), keyboard)
        return
    result = await teams.add_member(stores, callback.from_user.id, callback_data.value)
    if result == teams.TEAM_FULL:
        await callback.answer(text("team.cannot_add"), show_alert=True)
        return
    await callback.answer()
    await _show_editor(callback, stores)


@router.callback_query(TeamAction.filter(F.action == "replace"))
async def member_replaced(callback: CallbackQuery, callback_data: TeamAction, stores: Stores) -> None:
    if not await _is_owner(callback, callback_data.owner_id):
        return
    pokemon_id, slot = callback_data.value.split(".")
    result = await teams.replace_member(stores, callback.from_user.id, pokemon_id, int(slot))
    if result != teams.UPDATED:
        await callback.answer(text("team.cannot_add"), show_alert=True)
        return
    await callback.answer()
    await _show_editor(callback, stores)


@router.callback_query(TeamAction.filter(F.action == "remove"))
async def remove_pressed(callback: CallbackQuery, callback_data: TeamAction, stores: Stores) -> None:
    if not await _is_owner(callback, callback_data.owner_id):
        return
    team = await teams.active_team(stores, callback.from_user.id)
    if team is None:
        await _needs_partner(callback)
        return
    if not team.members:
        await callback.answer(text("team.team_empty"), show_alert=True)
        return
    await callback.answer()
    keyboard = remove_keyboard(callback.from_user.id, team.member_ids)
    await _show(callback, team_view.remove_text(team.members, team.display), keyboard)


@router.callback_query(TeamAction.filter(F.action == "drop"))
async def member_dropped(callback: CallbackQuery, callback_data: TeamAction, stores: Stores) -> None:
    if not await _is_owner(callback, callback_data.owner_id):
        return
    await teams.remove_member(stores, callback.from_user.id, callback_data.value)
    await callback.answer()
    await _show_editor(callback, stores)


@router.callback_query(TeamAction.filter(F.action == "order"))
async def order_pressed(callback: CallbackQuery, callback_data: TeamAction, stores: Stores) -> None:
    if not await _is_owner(callback, callback_data.owner_id):
        return
    team = await teams.active_team(stores, callback.from_user.id)
    if team is None:
        await _needs_partner(callback)
        return
    if len(team.members) < 2:
        await callback.answer(text("team.not_enough"), show_alert=True)
        return
    await callback.answer()
    await _show_order(callback, team)


@router.callback_query(TeamAction.filter(F.action == "first"))
async def first_chosen(callback: CallbackQuery, callback_data: TeamAction, stores: Stores) -> None:
    if not await _is_owner(callback, callback_data.owner_id):
        return
    team = await teams.active_team(stores, callback.from_user.id)
    if team is None:
        await _needs_partner(callback)
        return
    await callback.answer()
    await _show_order(callback, team, int(callback_data.value))


@router.callback_query(TeamAction.filter(F.action == "second"))
async def second_chosen(callback: CallbackQuery, callback_data: TeamAction, stores: Stores) -> None:
    if not await _is_owner(callback, callback_data.owner_id):
        return
    first, second = (int(slot) for slot in callback_data.value.split("."))
    await teams.swap_members(stores, callback.from_user.id, first, second)
    team = await teams.active_team(stores, callback.from_user.id)
    await callback.answer()
    if team is not None:
        await _show_order(callback, team)


@router.callback_query(TeamAction.filter(F.action == "shuffle"))
async def randomize_pressed(callback: CallbackQuery, callback_data: TeamAction, stores: Stores) -> None:
    if not await _is_owner(callback, callback_data.owner_id):
        return
    result = await teams.randomize(stores, callback.from_user.id)
    if result == teams.NOT_ENOUGH:
        await callback.answer(text("team.not_enough"), show_alert=True)
        return
    await callback.answer()
    await _show_editor(callback, stores)


@router.callback_query(TeamAction.filter(F.action == "save"))
async def save_pressed(callback: CallbackQuery, callback_data: TeamAction, stores: Stores) -> None:
    if not await _is_owner(callback, callback_data.owner_id):
        return
    result = await teams.save_as(stores, callback.from_user.id, int(callback_data.value))
    if result == teams.UPDATED:
        await callback.answer(text("team.saved", number=callback_data.value))
    else:
        await callback.answer()
    await _show_editor(callback, stores)
