import asyncio
import logging
import time
from functools import wraps
from html import escape
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware, Bot, F, Router
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest, TelegramNetworkError, TelegramRetryAfter
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from bot.game import creatures, encounters
from bot.game import safari as safari_rules
from bot.handlers.candy import offer_move
from bot.handlers.journey import JourneyRequired
from bot.handlers.private import private_only
from bot.services import evolving, hunting, reply_keyboard, safari, teams
from bot.storage.stores import Stores
from bot.ui import battle_view, team_view
from bot.ui.keyboards import (
    HuntAction,
    appeared_keyboard,
    ball_keyboard,
    battle_keyboard,
    caught_keyboard,
    ev_training_appeared_keyboard,
    expert_appeared_keyboard,
    main_keyboard,
    safari_action_keyboard,
    safari_appeared_keyboard,
    switch_keyboard,
    team_keyboard,
)
from bot.ui.texts import text


class KeepEncounterAlive(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[CallbackQuery, dict[str, Any]], Awaitable[Any]],
        event: CallbackQuery,
        data: dict[str, Any],
    ) -> Any:
        action = data["callback_data"]
        if event.from_user.id == action.owner_id:
            await hunting.keep_alive(data["stores"], action.owner_id, action.encounter_id)
        return await handler(event, data)


router = Router()
router.message.middleware(JourneyRequired())
router.callback_query.middleware(KeepEncounterAlive())

logger = logging.getLogger(__name__)

FLEE_CHECK_SECONDS = 5
ATTACKING_SECONDS = 1.0
CATCH_STEP_SECONDS = 1.2
SPAWNS_KEPT = 1000
HUNT_COOLDOWN_SECONDS = 0.4

_hunting_trainers: set[int] = set()
_acting_trainers: set[int] = set()
_last_spawn_message: dict[int, int] = {}
_last_hunt_at: dict[int, float] = {}
_artwork_file_ids: dict[tuple[int, bool], str] = {}


def _remember_hunt_time(trainer_id: int) -> None:
    if len(_last_hunt_at) >= SPAWNS_KEPT:
        _last_hunt_at.clear()
    _last_hunt_at[trainer_id] = time.monotonic()


def _remember_spawn(trainer_id: int, sent: Message) -> None:
    if len(_last_spawn_message) >= SPAWNS_KEPT:
        _last_spawn_message.clear()
    _last_spawn_message[trainer_id] = sent.message_id
    _remember_hunt_time(trainer_id)


def _is_repeat_hunt(trainer_id: int, message: Message) -> bool:
    if trainer_id in _hunting_trainers or message.message_id < _last_spawn_message.get(trainer_id, 0):
        return True
    last_at = _last_hunt_at.get(trainer_id)
    return last_at is not None and time.monotonic() - last_at < HUNT_COOLDOWN_SECONDS


async def _is_owner(callback: CallbackQuery, callback_data: HuntAction) -> bool:
    if callback.from_user.id == callback_data.owner_id and isinstance(callback.message, Message):
        return True
    await callback.answer(text("common.not_your_buttons"), show_alert=True)
    return False


def _one_action_at_a_time(handler: Callable[[CallbackQuery, HuntAction, Stores], Awaitable[None]]):
    @wraps(handler)
    async def wrapper(callback: CallbackQuery, callback_data: HuntAction, stores: Stores) -> None:
        if not await _is_owner(callback, callback_data):
            return
        trainer_id = callback.from_user.id
        if trainer_id in _acting_trainers:
            await callback.answer()
            return
        _acting_trainers.add(trainer_id)
        try:
            await handler(callback, callback_data, stores)
        finally:
            _acting_trainers.discard(trainer_id)

    return wrapper


async def _answered_fled(callback: CallbackQuery, callback_data: HuntAction, stores: Stores) -> bool:
    fled = await hunting.fled_encounter(stores, callback_data.owner_id, callback_data.encounter_id)
    if fled is None:
        return False
    await callback.answer()
    if callback.message is not None:
        target = {"chat_id": callback.message.chat.id, "message_id": callback.message.message_id}
        await announce_fled(callback.bot, {**fled, "message": target})
    return True


async def _battle_ended(callback: CallbackQuery, callback_data: HuntAction, stores: Stores) -> None:
    if await _answered_fled(callback, callback_data, stores):
        return
    await callback.answer(text("hunt.battle_ended"), show_alert=True)
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except TelegramBadRequest:
        pass


async def announce_ready(bot: Bot, stores: Stores, gains: list) -> None:
    for pokemon in await evolving.newly_ready(stores, gains):
        try:
            await bot.send_message(pokemon["trainer_id"], battle_view.ready_to_evolve_text(pokemon))
        except TelegramAPIError as error:
            logger.warning("Could not send evolution notice: %s", error)


async def _offer_moves(callback: CallbackQuery, stores: Stores, gains: list) -> None:
    learned = battle_view.learned_lines(gains)
    if learned:
        try:
            await callback.bot.send_message(callback.from_user.id, learned)
        except TelegramAPIError as error:
            logger.warning("Could not send learned moves: %s", error)
    await announce_ready(callback.bot, stores, gains)
    for gain in gains:
        for move in gain.waiting:
            await offer_move(
                callback.bot,
                stores,
                callback.from_user.id,
                callback.from_user.first_name,
                callback.message.chat.id,
                gain.pokemon,
                gain.new_level,
                move,
            )


def _moves_markup(callback: CallbackQuery, callback_data: HuntAction, state):
    return battle_keyboard(
        callback.from_user.id,
        callback_data.encounter_id,
        state.player["moves"],
        state.form_options,
        catchable=not state.encounter.get("expert"),
    )


def _screen(
    callback: CallbackQuery,
    state,
    opening: bool = False,
    action: str = "",
    choosing_next: bool = False,
) -> str:
    return battle_view.battle_text(
        state,
        callback.from_user.id,
        callback.from_user.first_name,
        opening=opening,
        action=action,
        choosing_next=choosing_next,
    )


def _switch_markup(callback: CallbackQuery, callback_data: HuntAction, state):
    return switch_keyboard(
        callback.from_user.id,
        callback_data.encounter_id,
        state.team_ids,
        state.encounter.get("player_id"),
        state.fainted_ids,
        state.can_go_back,
    )


def _fainted_ending(
    callback: CallbackQuery,
    callback_data: HuntAction,
    state,
    event,
    lost: bool,
    lead: str = "",
):
    fainting = battle_view.fainting_text(state, event)
    action = f"{lead}\n\n{fainting}" if lead else fainting
    if not lost:
        body = _screen(callback, state, action=action, choosing_next=True)
        return body, _switch_markup(callback, callback_data, state)
    return "\n\n".join([action, battle_view.all_fainted_text(state.encounter)]), None


async def _show_attacking(message: Message, body: str) -> None:
    try:
        await message.edit_text(body, reply_markup=None)
    except (TelegramBadRequest, TelegramNetworkError, TelegramRetryAfter):
        return
    await asyncio.sleep(ATTACKING_SECONDS)


async def _show_turn_end(message: Message, body: str, reply_markup=None) -> None:
    try:
        await message.edit_text(body, reply_markup=reply_markup)
    except TelegramRetryAfter as flood:
        await asyncio.sleep(flood.retry_after)
        await message.edit_text(body, reply_markup=reply_markup)


async def announce_fled(bot: Bot, encounter: dict) -> None:
    target = encounter.get("message")
    if target is None:
        return
    body = battle_view.fled_text(encounter)
    try:
        try:
            await bot.edit_message_text(text=body, reply_markup=None, **target)
        except TelegramBadRequest:
            await bot.edit_message_caption(caption=body, reply_markup=None, **target)
    except TelegramAPIError as error:
        logger.warning("Could not announce fled encounter: %s", error)


def _caught_parts(name: str, outcome) -> list[str]:
    parts = [text("hunt.caught", name=name)]
    if outcome.held_stone:
        parts.append(battle_view.held_stone_text(name, outcome.held_stone))
    if outcome.event_reward:
        parts.append(text("hunt.event_reward", amount=outcome.event_reward))
    if outcome.money_limited:
        parts.append(text("hunt.earning_limit"))
    return parts


async def _encounter_gone(callback: CallbackQuery, callback_data: HuntAction, stores: Stores) -> None:
    if await _answered_fled(callback, callback_data, stores):
        return
    await callback.answer(text("hunt.encounter_inactive"), show_alert=True)


async def flee_idle_encounters(stores: Stores) -> None:
    while True:
        try:
            while await hunting.next_fled_encounter(stores) is not None:
                pass
        except Exception:
            logger.exception("Could not check idle encounters")
        await asyncio.sleep(FLEE_CHECK_SECONDS)


async def _remember(stores: Stores, trainer_id: int, encounter_id: str, sent: Message) -> None:
    await hunting.remember_message(stores, trainer_id, encounter_id, sent.chat.id, sent.message_id)


async def _animate_catch(message: Message, ball: str, stars: int, caught: bool) -> None:
    for frame in battle_view.catch_frames(ball, stars, caught):
        try:
            await message.edit_text(frame, reply_markup=None)
        except (TelegramBadRequest, TelegramNetworkError, TelegramRetryAfter):
            return
        await asyncio.sleep(CATCH_STEP_SECONDS)


async def _show_throw_result(message: Message, body: str, reply_markup=None) -> Message:
    try:
        await _show_turn_end(message, body, reply_markup)
    except TelegramBadRequest:
        return await message.answer(body, reply_markup=reply_markup)
    return message


async def _finish_turn(callback: CallbackQuery, callback_data: HuntAction, outcome: hunting.TurnOutcome) -> None:
    state = outcome.state
    last_event = outcome.result.events[-1]
    if outcome.next_state:
        next_state = outcome.next_state
        sent_out = text("hunt.expert_sent_out", name=battle_view.wild_name(next_state.encounter))
        ending = battle_view.expert_fainted_text(state.encounter, sent_out)
        action = f"{battle_view.finishing_text(state, last_event)}\n\n{ending}"
        await _show_turn_end(
            callback.message,
            _screen(callback, next_state, action=action),
            _moves_markup(callback, callback_data, next_state),
        )
        return
    action = battle_view.action_text(state, last_event)
    if outcome.wild_fainted:
        finishing = battle_view.finishing_text(state, last_event)
        if state.encounter.get("expert"):
            ending = battle_view.expert_fainted_text(state.encounter, text("hunt.expert_defeated"))
        else:
            ending = text("hunt.wild_fainted", name=battle_view.wild_name(state.encounter))
        rewards = [text("hunt.reward", amount=outcome.reward)] if outcome.reward else []
        if outcome.money_limited:
            rewards.append(text("hunt.battle_limit"))
        await _show_turn_end(callback.message, "\n\n".join([finishing, ending, *rewards]))
    elif outcome.player_fainted:
        body, markup = _fainted_ending(callback, callback_data, state, last_event, outcome.lost)
        await _show_turn_end(callback.message, body, markup)
    else:
        await _show_turn_end(
            callback.message,
            _screen(callback, state, action=action),
            _moves_markup(callback, callback_data, state),
        )


@router.message(Command("hunt"), F.from_user)
@private_only("hunt")
async def hunt_command(message: Message, stores: Stores) -> None:
    trainer_id = message.from_user.id
    if _is_repeat_hunt(trainer_id, message):
        return
    _hunting_trainers.add(trainer_id)
    _remember_hunt_time(trainer_id)
    try:
        await _do_hunt(message, stores, trainer_id)
    finally:
        _hunting_trainers.discard(trainer_id)


async def _show_found(message: Message, hunt: hunting.HuntResult) -> None:
    if hunt.found_egg:
        await message.answer(text("hunt.found_egg"))
        return
    if hunt.found_tm:
        await message.answer(text("hunt.found_tm", number=hunt.found_tm))
        return
    caption = battle_view.found_stone_text(hunt.found_stone)
    try:
        await message.bot.copy_message(
            message.chat.id,
            encounters.STONE_IMAGES_CHANNEL,
            encounters.stone_image_id(hunt.found_stone),
            caption=caption,
        )
    except TelegramAPIError:
        await message.answer(caption)


async def _show_expert(message: Message, stores: Stores, trainer_id: int, encounter_id: str) -> None:
    sent = await message.reply(
        text("hunt.expert_challenge"),
        reply_markup=expert_appeared_keyboard(trainer_id, encounter_id),
    )
    await _remember(stores, trainer_id, encounter_id, sent)
    team = await teams.active_team(stores, trainer_id)
    shown = await message.reply(team_view.team_lines(team.members, team.display), reply_markup=team_keyboard(trainer_id))
    _remember_spawn(trainer_id, shown)


async def _send_spawn(message: Message, wild: dict, caption: str, keyboard: InlineKeyboardMarkup) -> Message:
    shiny = wild.get("shiny", False)
    key = (wild["dex_id"], shiny)
    file_id = _artwork_file_ids.get(key)
    if file_id:
        try:
            return await message.reply_photo(file_id, caption=caption, reply_markup=keyboard)
        except TelegramBadRequest:
            _artwork_file_ids.pop(key, None)
    try:
        sent = await message.reply_photo(battle_view.artwork(*key), caption=caption, reply_markup=keyboard)
    except TelegramBadRequest:
        return await message.reply(caption, reply_markup=keyboard)
    _artwork_file_ids[key] = sent.photo[-1].file_id
    return sent


async def _do_hunt(message: Message, stores: Stores, trainer_id: int) -> None:
    hunt = await hunting.start_hunt(stores, trainer_id)
    if hunt.status == hunting.NEEDS_PARTNER:
        await message.reply(text("common.start_journey"))
        return
    if hunt.status == hunting.EMPTY_TEAM:
        await message.reply(text("hunt.empty_team"))
        return
    if hunt.status == hunting.IN_BATTLE:
        await message.reply(text("hunt.already_in_battle"))
        return
    if hunt.status == hunting.IN_TRADE:
        await message.reply(text("trade.locked"))
        return
    if hunt.status == hunting.SAFARI_REMOVED:
        await message.reply(text("safari.removed", region=hunt.region))
        return
    if hunt.status == hunting.EV_TRAINING_FINISHED:
        await message.reply(text("ev_training.session_finished"))
        return

    if await reply_keyboard.mark_open(stores, trainer_id):
        await message.answer(text("common.keyboard_opened"), reply_markup=main_keyboard())

    if hunt.status == hunting.MOM_GIFT:
        await message.reply(battle_view.mom_gift_text())
        return

    if hunt.status == hunting.FOUND:
        await _show_found(message, hunt)
        return

    if hunt.status == hunting.EXPERT_READY:
        await _show_expert(message, stores, trainer_id, hunt.encounter["id"])
        return

    if hunt.status == hunting.SAFARI_READY:
        caption = battle_view.safari_appeared_text(
            hunt.encounter, hunt.caught_before, hunt.hunts, safari_rules.HUNT_LIMIT, hunt.balls
        )
        keyboard = safari_appeared_keyboard(trainer_id, hunt.encounter["id"], hunt.encounter["wild"]["dex_id"])
    elif hunt.status == hunting.EV_TRAINING_READY:
        caption = battle_view.ev_training_appeared_text(hunt.encounter, hunt.caught_before)
        keyboard = ev_training_appeared_keyboard(trainer_id, hunt.encounter["id"], hunt.encounter["wild"]["dex_id"])
    else:
        caption = battle_view.appeared_text(hunt.encounter, hunt.caught_before)
        keyboard = appeared_keyboard(trainer_id, hunt.encounter["id"], hunt.encounter["wild"]["dex_id"])
    wild = hunt.encounter["wild"]
    if wild.get("shiny"):
        await message.answer(text("hunt.shiny_found"))
    sent = await _send_spawn(message, wild, caption, keyboard)
    _remember_spawn(trainer_id, sent)
    await _remember(stores, trainer_id, hunt.encounter["id"], sent)


@router.callback_query(HuntAction.filter(F.action == "ev"))
async def ev_yield_pressed(callback: CallbackQuery, callback_data: HuntAction, stores: Stores) -> None:
    if await _answered_fled(callback, callback_data, stores):
        return
    await callback.answer(battle_view.ev_yield_alert(int(callback_data.value)), show_alert=True)


@router.callback_query(HuntAction.filter(F.action == "safari_catch"))
async def safari_catch_pressed(callback: CallbackQuery, callback_data: HuntAction, stores: Stores) -> None:
    if not await _is_owner(callback, callback_data):
        return

    opened = await safari.begin_catch(stores, callback.from_user.id, callback_data.encounter_id)
    if opened is None:
        if await hunting.current_state(stores, callback.from_user.id, callback_data.encounter_id) is not None:
            await callback.answer()
        else:
            await _encounter_gone(callback, callback_data, stores)
        return

    await callback.answer()
    _, balls = opened
    sent = await callback.message.answer(
        battle_view.safari_prompt_text(balls),
        reply_markup=safari_action_keyboard(callback.from_user.id, callback_data.encounter_id),
    )
    await _remember(stores, callback.from_user.id, callback_data.encounter_id, sent)


@router.callback_query(HuntAction.filter(F.action == "safari_throw"))
@_one_action_at_a_time
async def safari_ball_thrown(callback: CallbackQuery, callback_data: HuntAction, stores: Stores) -> None:
    outcome = await safari.throw_ball(stores, callback.from_user.id, callback_data.encounter_id)
    if outcome is None:
        await _battle_ended(callback, callback_data, stores)
        return

    await callback.answer()
    message = callback.message
    await _animate_catch(message, safari_rules.BALL, outcome.stars, outcome.caught)

    name = battle_view.wild_name({"wild": outcome.wild})
    ball = safari_rules.BALL.title()
    if outcome.caught:
        parts = _caught_parts(name, outcome)
    elif outcome.fled:
        parts = [text("hunt.ball_failed", ball=ball, name=name)]
    else:
        parts = [text("safari.failed")]
    if outcome.out_of_balls:
        parts.append(text("safari.out_of_balls", region=outcome.region))

    markup = None
    if outcome.caught:
        markup = caught_keyboard(callback.from_user.id, outcome.encounter_id, outcome.wild["dex_id"])
    elif not outcome.fled and not outcome.out_of_balls:
        parts.append(battle_view.safari_prompt_text(outcome.balls))
        markup = safari_action_keyboard(callback.from_user.id, outcome.encounter_id)
    sent = await _show_throw_result(message, "\n\n".join(parts), markup)
    if not outcome.caught and not outcome.fled and not outcome.out_of_balls:
        await _remember(stores, callback.from_user.id, outcome.encounter_id, sent)


@router.callback_query(HuntAction.filter(F.action == "battle"))
async def battle_pressed(
    callback: CallbackQuery,
    callback_data: HuntAction,
    stores: Stores,
) -> None:
    if not await _is_owner(callback, callback_data):
        return

    state = await hunting.begin_battle(stores, callback.from_user.id, callback_data.encounter_id)
    if state is None:
        if await hunting.current_state(stores, callback.from_user.id, callback_data.encounter_id) is not None:
            await callback.answer()
        elif callback_data.value.isdigit():
            await _encounter_gone(callback, callback_data, stores)
        else:
            await _battle_ended(callback, callback_data, stores)
        return

    await callback.answer()
    sent = await callback.message.answer(
        _screen(callback, state, opening=True),
        reply_markup=_moves_markup(callback, callback_data, state),
    )
    await _remember(stores, callback.from_user.id, callback_data.encounter_id, sent)


@router.callback_query(HuntAction.filter(F.action == "expert"))
async def expert_battle_pressed(callback: CallbackQuery, callback_data: HuntAction, stores: Stores) -> None:
    if not await _is_owner(callback, callback_data):
        return

    start = await hunting.begin_expert_battle(stores, callback.from_user.id, callback_data.encounter_id)
    if start is None:
        if await hunting.current_state(stores, callback.from_user.id, callback_data.encounter_id) is not None:
            await callback.answer()
        else:
            await _encounter_gone(callback, callback_data, stores)
        return
    if start.status == hunting.EMPTY_TEAM:
        await callback.answer(text("hunt.empty_team"), show_alert=True)
        return

    await callback.answer()
    sent = await callback.message.answer(
        _screen(callback, start.state, opening=True),
        reply_markup=_moves_markup(callback, callback_data, start.state),
    )
    await _remember(stores, callback.from_user.id, callback_data.encounter_id, sent)


@router.callback_query(HuntAction.filter(F.action == "move"))
@_one_action_at_a_time
async def move_pressed(
    callback: CallbackQuery,
    callback_data: HuntAction,
    stores: Stores,
) -> None:
    outcome = await hunting.use_move(
        stores,
        callback.from_user.id,
        callback_data.encounter_id,
        int(callback_data.value),
    )
    if outcome is None:
        await _battle_ended(callback, callback_data, stores)
        return

    await callback.answer()
    for event in outcome.result.events[:-1]:
        await _show_attacking(callback.message, battle_view.attacking_text(outcome.state, event))
    await _finish_turn(callback, callback_data, outcome)
    await _offer_moves(callback, stores, outcome.gains)


async def send_form_change(message: Message, before: dict, option) -> None:
    caption = battle_view.form_change_text(before, option)
    image = battle_view.artwork(option.form_id, before.get("shiny", False))
    try:
        await message.reply_photo(image, caption=caption)
    except TelegramBadRequest:
        await message.reply(caption)


@router.callback_query(HuntAction.filter(F.action == "form"))
async def form_pressed(callback: CallbackQuery, callback_data: HuntAction, stores: Stores) -> None:
    if not await _is_owner(callback, callback_data):
        return

    outcome = await hunting.change_form(
        stores,
        callback.from_user.id,
        callback_data.encounter_id,
        int(callback_data.value),
    )
    if outcome is None:
        await _battle_ended(callback, callback_data, stores)
        return
    if outcome.status == hunting.CANNOT_CHANGE_FORM:
        await callback.answer(text("battle.form_unavailable"), show_alert=True)
        return

    await callback.answer()
    await send_form_change(callback.message, outcome.before, outcome.option)
    await _show_turn_end(
        callback.message,
        _screen(callback, outcome.state),
        _moves_markup(callback, callback_data, outcome.state),
    )


@router.callback_query(HuntAction.filter(F.action == "run"))
async def run_pressed(
    callback: CallbackQuery,
    callback_data: HuntAction,
    stores: Stores,
) -> None:
    if not await _is_owner(callback, callback_data):
        return

    if not await hunting.run_away(stores, callback.from_user.id, callback_data.encounter_id):
        await _battle_ended(callback, callback_data, stores)
        return

    await callback.answer()
    await callback.message.edit_text(text("hunt.got_away"), reply_markup=None)


@router.callback_query(HuntAction.filter(F.action == "pokemons"))
async def pokemons_pressed(
    callback: CallbackQuery,
    callback_data: HuntAction,
    stores: Stores,
) -> None:
    if not await _is_owner(callback, callback_data):
        return

    state = await hunting.current_state(stores, callback.from_user.id, callback_data.encounter_id)
    if state is None:
        await _battle_ended(callback, callback_data, stores)
        return

    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=_switch_markup(callback, callback_data, state))


@router.callback_query(HuntAction.filter(F.action == "noop"))
async def empty_slot_pressed(callback: CallbackQuery) -> None:
    await callback.answer()


@router.callback_query(HuntAction.filter(F.action == "team"))
async def view_team_pressed(
    callback: CallbackQuery,
    callback_data: HuntAction,
    stores: Stores,
) -> None:
    if not await _is_owner(callback, callback_data):
        return

    view = await hunting.team_view(stores, callback.from_user.id, callback_data.encounter_id)
    if view is None:
        await _battle_ended(callback, callback_data, stores)
        return

    await callback.answer(battle_view.team_alert(view), show_alert=True)


@router.callback_query(HuntAction.filter(F.action == "switch"))
@_one_action_at_a_time
async def switch_pressed(
    callback: CallbackQuery,
    callback_data: HuntAction,
    stores: Stores,
) -> None:
    outcome = await hunting.switch_pokemon(
        stores,
        callback.from_user.id,
        callback_data.encounter_id,
        int(callback_data.value),
    )
    if outcome is None:
        await _battle_ended(callback, callback_data, stores)
        return
    if outcome.status == hunting.CANNOT_SWITCH:
        await callback.answer(text("hunt.cannot_switch"), show_alert=True)
        return

    await callback.answer()
    state = outcome.turn.state
    if outcome.forced:
        sent_out = text("battle.sent_out", name=escape(creatures.shown_name(state.player)))
        await _show_turn_end(
            callback.message,
            _screen(callback, state, action=sent_out),
            _moves_markup(callback, callback_data, state),
        )
        return
    await _show_attacking(callback.message, battle_view.switched_text(state, outcome.called_back))
    await _finish_turn(callback, callback_data, outcome.turn)
    await _offer_moves(callback, stores, outcome.turn.gains)


@router.callback_query(HuntAction.filter(F.action == "balls"))
async def poke_ball_pressed(
    callback: CallbackQuery,
    callback_data: HuntAction,
    stores: Stores,
) -> None:
    if not await _is_owner(callback, callback_data):
        return

    state = await hunting.current_state(stores, callback.from_user.id, callback_data.encounter_id)
    if state is None:
        await _battle_ended(callback, callback_data, stores)
        return
    if state.encounter.get("ev_training"):
        await callback.answer(text("ev_training.no_balls"))
        return
    if state.encounter.get("expert"):
        await callback.answer(text("challenge.no_catching"))
        return
    if not state.has_throwable_ball:
        await callback.answer(text("hunt.no_balls"), show_alert=True)
        return

    encounter = state.encounter
    if encounter["wild_hp"] >= creatures.stats_of(encounter["wild"])["hp"]:
        await callback.answer(text("hunt.lower_hp_hint", name=battle_view.wild_name(encounter)))
    else:
        await callback.answer()
    await callback.message.edit_text(
        _screen(callback, state),
        reply_markup=ball_keyboard(callback.from_user.id, callback_data.encounter_id, state.balls),
    )


@router.callback_query(HuntAction.filter(F.action == "back"))
async def back_pressed(
    callback: CallbackQuery,
    callback_data: HuntAction,
    stores: Stores,
) -> None:
    if not await _is_owner(callback, callback_data):
        return

    state = await hunting.current_state(stores, callback.from_user.id, callback_data.encounter_id)
    if state is None:
        await _battle_ended(callback, callback_data, stores)
        return

    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=_moves_markup(callback, callback_data, state))


@router.callback_query(HuntAction.filter(F.action == "throw"))
@_one_action_at_a_time
async def ball_thrown(
    callback: CallbackQuery,
    callback_data: HuntAction,
    stores: Stores,
) -> None:
    outcome = await hunting.throw_ball(
        stores,
        callback.from_user.id,
        callback_data.encounter_id,
        callback_data.value,
    )
    if outcome is None:
        await _battle_ended(callback, callback_data, stores)
        return
    if outcome.status == hunting.NO_BALL:
        await callback.answer(text("hunt.no_ball_left"), show_alert=True)
        return

    await callback.answer()
    message = callback.message
    state = outcome.state
    name = battle_view.wild_name(state.encounter)
    await _animate_catch(message, callback_data.value, outcome.stars, outcome.caught)

    if outcome.caught:
        parts = _caught_parts(name, outcome)
        await _show_throw_result(
            message,
            "\n\n".join(parts),
            caught_keyboard(callback.from_user.id, state.encounter["id"], state.encounter["wild"]["dex_id"]),
        )
        await _offer_moves(callback, stores, outcome.gains)
        return

    if outcome.fled:
        parts = [text("hunt.ball_failed", ball=callback_data.value.title(), name=name)]
        if outcome.drop:
            parts.append(battle_view.flee_drop_text(outcome.drop))
        if outcome.money_limited:
            parts.append(text("hunt.earning_limit"))
        await _show_throw_result(message, "\n\n".join(parts))
        await _offer_moves(callback, stores, outcome.gains)
        return

    broke_free = text("hunt.broke_free", name=name)
    action = f"{broke_free}\n\n{battle_view.action_text(state, outcome.counter.events[-1])}"
    if outcome.player_fainted:
        last_event = outcome.counter.events[-1]
        body, markup = _fainted_ending(
            callback, callback_data, state, last_event, outcome.lost, lead=broke_free
        )
        sent = await _show_throw_result(message, body, markup)
        if not outcome.lost:
            await _remember(stores, callback.from_user.id, callback_data.encounter_id, sent)
        await _offer_moves(callback, stores, outcome.gains)
        return
    sent = await _show_throw_result(
        message,
        _screen(callback, state, action=action),
        _moves_markup(callback, callback_data, state),
    )
    await _remember(stores, callback.from_user.id, callback_data.encounter_id, sent)
