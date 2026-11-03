import asyncio
import logging
from html import escape

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest, TelegramRetryAfter
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from aiogram.utils.deep_linking import create_start_link

from bot.game import challenges as rules
from bot.game import creatures, pokedex
from bot.handlers.candy import offer_move
from bot.handlers.cooldown import ButtonCooldown
from bot.handlers.hunt import announce_fled, announce_ready, send_form_change
from bot.handlers.journey import JourneyRequired
from bot.handlers.team import EDITOR_LINK_COMMAND
from bot.services import challenging
from bot.storage.stores import Stores
from bot.ui import battle_view, challenge_view
from bot.ui.keyboards import (
    ChallengeAction,
    challenge_battle_keyboard,
    challenge_level_ranges_keyboard,
    challenge_levels_keyboard,
    challenge_number_keyboard,
    challenge_prompt_keyboard,
    challenge_settings_keyboard,
    challenge_switch_keyboard,
)
from bot.ui.texts import text

EXPIRY_CHECK_SECONDS = 5

router = Router()
router.message.middleware(JourneyRequired())
router.callback_query.middleware(ButtonCooldown())

logger = logging.getLogger(__name__)


async def _show(callback: CallbackQuery, body: str, markup: InlineKeyboardMarkup | None = None) -> None:
    try:
        await callback.message.edit_text(body, reply_markup=markup)
    except TelegramRetryAfter as flood:
        await asyncio.sleep(flood.retry_after)
        await callback.message.edit_text(body, reply_markup=markup)
    except TelegramBadRequest as error:
        if "message is not modified" not in str(error):
            raise


async def _ended(callback: CallbackQuery) -> None:
    await callback.answer(text("hunt.battle_ended"), show_alert=True)


async def _action_lost(callback: CallbackQuery, challenge_id: str, stores: Stores) -> None:
    challenge = await challenging.get(stores, challenge_id)
    if challenge is not None and challenge["state"] == rules.BATTLING:
        await callback.answer()
    else:
        await _ended(callback)


async def _participant(callback: CallbackQuery, callback_data: ChallengeAction, stores: Stores) -> dict | None:
    challenge = await challenging.get(stores, callback_data.challenge_id)
    if challenge is None or not isinstance(callback.message, Message):
        await _ended(callback)
        return None
    if rules.side_named(challenge, callback.from_user.id) is None:
        await callback.answer(text("common.not_your_buttons"), show_alert=True)
        return None
    return challenge


async def _in_battle(callback: CallbackQuery, callback_data: ChallengeAction, stores: Stores) -> dict | None:
    challenge = await _participant(callback, callback_data, stores)
    if challenge is None:
        return None
    if challenge["state"] != rules.BATTLING:
        await _ended(callback)
        return None
    return challenge


async def _on_turn(callback: CallbackQuery, callback_data: ChallengeAction, stores: Stores) -> dict | None:
    challenge = await _in_battle(callback, callback_data, stores)
    if challenge is None:
        return None
    if rules.side_named(challenge, callback.from_user.id) != challenge["current"]:
        await callback.answer(text("challenge.not_your_turn"))
        return None
    return challenge


async def _waiting_for_challenger(
    callback: CallbackQuery,
    callback_data: ChallengeAction,
    stores: Stores,
) -> dict | None:
    challenge = await _participant(callback, callback_data, stores)
    if challenge is None:
        return None
    if challenge["state"] != rules.WAITING:
        await _ended(callback)
        return None
    if callback.from_user.id != challenge[rules.CHALLENGER]["id"]:
        await callback.answer(text("challenge.settings_only"), show_alert=True)
        return None
    return challenge


async def _prompt_markup(bot: Bot, challenge: dict) -> InlineKeyboardMarkup:
    link = await create_start_link(bot, EDITOR_LINK_COMMAND)
    return challenge_prompt_keyboard(str(challenge["_id"]), link, bool(challenge["ready"]))


async def _show_prompt(callback: CallbackQuery, challenge: dict) -> None:
    await _show(callback, challenge_view.prompt_text(challenge), await _prompt_markup(callback.bot, challenge))


async def _show_settings(callback: CallbackQuery, challenge: dict) -> None:
    await _show(callback, challenge_view.settings_text(challenge), challenge_settings_keyboard(str(challenge["_id"])))


async def _send_learned(bot: Bot, trainer_id: int, pokemon: dict, move: str) -> None:
    body = text("hunt.move_learned", name=escape(creatures.shown_name(pokemon)), move=pokedex.display_name(move))
    try:
        await bot.send_message(trainer_id, body)
    except TelegramAPIError as error:
        logger.warning("Could not send learned move: %s", error)


async def _announce_moves(bot: Bot, stores: Stores, challenge: dict, gains: list) -> None:
    await announce_ready(bot, stores, gains)
    for gain in gains:
        trainer_id = gain.pokemon["trainer_id"]
        for move in gain.learned:
            await _send_learned(bot, trainer_id, gain.pokemon, move)
        trainer_name = challenge[rules.side_named(challenge, trainer_id)]["name"]
        for move in gain.waiting:
            await offer_move(bot, stores, trainer_id, trainer_name, challenge["chat_id"], gain.pokemon, gain.new_level, move)


def _setting_choice(value: str) -> tuple[str, int] | None:
    name, _, number = value.partition("=")
    if name not in rules.SETTING_VALUES or not number.isdigit():
        return None
    return name, int(number)


def _moves_markup(challenge: dict) -> InlineKeyboardMarkup:
    side = challenge[challenge["current"]]
    return challenge_battle_keyboard(str(challenge["_id"]), rules.active(side)["pokemon"]["moves"], rules.form_options(side))


def _switch_markup(challenge: dict) -> InlineKeyboardMarkup:
    side = challenge[challenge["current"]]
    return challenge_switch_keyboard(str(challenge["_id"]), side["team"], challenge["phase"] == rules.MOVE)


def _battle_markup(challenge: dict) -> InlineKeyboardMarkup:
    return _moves_markup(challenge) if challenge["phase"] == rules.MOVE else _switch_markup(challenge)


@router.message(Command("challenge"), F.from_user)
async def challenge_command(message: Message, stores: Stores) -> None:
    replied = message.reply_to_message
    target = replied.from_user if replied and not replied.forum_topic_created else None
    if target is None:
        await message.reply(text("challenge.usage"))
        return
    if target.id == message.from_user.id:
        await message.reply(text("challenge.self"))
        return
    if target.is_bot:
        await message.reply(text("challenge.bot"))
        return

    result = await challenging.request(
        stores,
        message.from_user.id,
        message.from_user.first_name,
        target.id,
        target.first_name,
        message.chat.id,
    )
    if result.status != challenging.CREATED:
        await message.reply(text(f"challenge.{result.status}"))
        return
    challenge = await challenging.get(stores, result.challenge_id)
    sent = await message.reply(
        challenge_view.prompt_text(challenge),
        reply_markup=await _prompt_markup(message.bot, challenge),
    )
    await challenging.remember_message(stores, result.challenge_id, sent.message_id)


@router.message(Command("settingsinfo"))
async def settings_info(message: Message) -> None:
    await message.reply(text("challenge.settings_info"))


@router.callback_query(ChallengeAction.filter(F.action == "ready"))
async def ready_pressed(callback: CallbackQuery, callback_data: ChallengeAction, stores: Stores) -> None:
    challenge = await _participant(callback, callback_data, stores)
    if challenge is None:
        return
    if challenge["state"] == rules.JOINING:
        await callback.answer()
        return
    if challenge["state"] != rules.WAITING:
        await _ended(callback)
        return

    result = await challenging.press_ready(stores, challenge, callback.from_user.id)
    for encounter in result.fled:
        await announce_fled(callback.bot, encounter)
    if result.status == challenging.ALREADY_STARTING:
        await callback.answer()
    elif result.status == challenging.ENDED:
        await _ended(callback)
    elif result.status == challenging.WAITING:
        await callback.answer()
        await _show_prompt(callback, result.challenge)
    elif result.status == challenging.STARTED:
        await callback.answer()
        started = result.challenge
        lead = challenge_view.opening_lead(started, result.speed_tie)
        await _show(callback, challenge_view.screen_text(started, lead), _moves_markup(started))
    else:
        await callback.answer(text(f"challenge.{result.status}"), show_alert=True)
        if result.challenge is not None:
            await _show_prompt(callback, result.challenge)


@router.callback_query(ChallengeAction.filter(F.action == "settings"))
async def settings_pressed(callback: CallbackQuery, callback_data: ChallengeAction, stores: Stores) -> None:
    challenge = await _waiting_for_challenger(callback, callback_data, stores)
    if challenge is None:
        return
    await callback.answer()
    await _show_settings(callback, challenge)


@router.callback_query(ChallengeAction.filter(F.action == "toggle"))
async def setting_toggled(callback: CallbackQuery, callback_data: ChallengeAction, stores: Stores) -> None:
    challenge = await _waiting_for_challenger(callback, callback_data, stores)
    name = callback_data.value
    if challenge is None or name not in rules.TOGGLE_SETTINGS:
        return
    updated = await challenging.set_setting(stores, challenge, name, not challenge["settings"][name])
    if updated is None:
        await _ended(callback)
        return
    await callback.answer()
    await _show_settings(callback, updated)


@router.callback_query(ChallengeAction.filter(F.action == "choose"))
async def setting_opened(callback: CallbackQuery, callback_data: ChallengeAction, stores: Stores) -> None:
    challenge = await _waiting_for_challenger(callback, callback_data, stores)
    name = callback_data.value
    if challenge is None or name not in rules.SETTING_VALUES:
        return
    await callback.answer()
    make_markup = challenge_level_ranges_keyboard if name in rules.LEVEL_SETTINGS else challenge_number_keyboard
    await _show(callback, challenge_view.picker_text(challenge, name), make_markup(callback_data.challenge_id, name))


@router.callback_query(ChallengeAction.filter(F.action == "range"))
async def level_range_opened(callback: CallbackQuery, callback_data: ChallengeAction, stores: Stores) -> None:
    challenge = await _waiting_for_challenger(callback, callback_data, stores)
    choice = _setting_choice(callback_data.value)
    if challenge is None or choice is None:
        return
    name, start = choice
    await callback.answer()
    await _show(
        callback,
        challenge_view.picker_text(challenge, name),
        challenge_levels_keyboard(callback_data.challenge_id, name, start),
    )


@router.callback_query(ChallengeAction.filter(F.action == "set"))
async def setting_chosen(callback: CallbackQuery, callback_data: ChallengeAction, stores: Stores) -> None:
    challenge = await _waiting_for_challenger(callback, callback_data, stores)
    choice = _setting_choice(callback_data.value)
    if challenge is None or choice is None or choice[1] not in rules.SETTING_VALUES[choice[0]]:
        return
    name, value = choice
    if not rules.fits_together(challenge["settings"], name, value):
        await callback.answer(text("challenge.settings_conflict"), show_alert=True)
        return
    updated = await challenging.set_setting(stores, challenge, name, value)
    if updated is None:
        await _ended(callback)
        return
    await callback.answer()
    await _show_settings(callback, updated)


@router.callback_query(ChallengeAction.filter(F.action == "save"))
async def settings_saved(callback: CallbackQuery, callback_data: ChallengeAction, stores: Stores) -> None:
    challenge = await _waiting_for_challenger(callback, callback_data, stores)
    if challenge is None:
        return
    await challenging.save_settings(stores, challenge)
    await callback.answer(text("challenge.settings_saved"))
    await _show_prompt(callback, challenge)


@router.callback_query(ChallengeAction.filter(F.action == "prompt"))
async def prompt_pressed(callback: CallbackQuery, callback_data: ChallengeAction, stores: Stores) -> None:
    challenge = await _waiting_for_challenger(callback, callback_data, stores)
    if challenge is None:
        return
    await callback.answer()
    await _show_prompt(callback, challenge)


@router.callback_query(ChallengeAction.filter(F.action == "move"))
async def move_pressed(callback: CallbackQuery, callback_data: ChallengeAction, stores: Stores) -> None:
    challenge = await _on_turn(callback, callback_data, stores)
    if challenge is None:
        return
    outcome = await challenging.use_move(stores, challenge, int(callback_data.value))
    if outcome is None:
        await _action_lost(callback, callback_data.challenge_id, stores)
        return
    await callback.answer()
    lead = challenge_view.move_lead(outcome)
    if outcome.challenge["state"] != rules.BATTLING:
        await _show(callback, challenge_view.result_text(outcome.challenge, lead))
    else:
        await _show(callback, challenge_view.screen_text(outcome.challenge, lead), _battle_markup(outcome.challenge))
    await _announce_moves(callback.bot, stores, outcome.challenge, outcome.gains)


@router.callback_query(ChallengeAction.filter(F.action == "form"))
async def form_pressed(callback: CallbackQuery, callback_data: ChallengeAction, stores: Stores) -> None:
    challenge = await _on_turn(callback, callback_data, stores)
    if challenge is None:
        return
    outcome = await challenging.change_form(stores, challenge, int(callback_data.value))
    if outcome is None:
        await _action_lost(callback, callback_data.challenge_id, stores)
        return
    if outcome.status != challenging.FORM_CHANGED:
        await callback.answer(text("battle.form_unavailable"), show_alert=True)
        return
    await callback.answer()
    await send_form_change(callback.message, outcome.before, outcome.option)
    await _show(callback, challenge_view.screen_text(outcome.challenge), _battle_markup(outcome.challenge))


@router.callback_query(ChallengeAction.filter(F.action == "balls"))
async def balls_pressed(callback: CallbackQuery, callback_data: ChallengeAction, stores: Stores) -> None:
    if await _in_battle(callback, callback_data, stores) is not None:
        await callback.answer(text("challenge.no_catching"))


@router.callback_query(ChallengeAction.filter(F.action == "run"))
async def run_pressed(callback: CallbackQuery, callback_data: ChallengeAction, stores: Stores) -> None:
    if await _in_battle(callback, callback_data, stores) is None:
        return
    outcome = await challenging.offer_draw(stores, callback_data.challenge_id, callback.from_user.id)
    if outcome is None:
        await _ended(callback)
        return
    if outcome.status == challenging.OFFERED:
        await callback.answer(text("challenge.draw_offered"))
        return
    await callback.answer()
    await _show(callback, challenge_view.result_text(outcome.settled.challenge, gains=outcome.settled.gains))
    await _announce_moves(callback.bot, stores, outcome.settled.challenge, outcome.settled.gains)


@router.callback_query(ChallengeAction.filter(F.action == "pokemon"))
async def pokemon_pressed(callback: CallbackQuery, callback_data: ChallengeAction, stores: Stores) -> None:
    challenge = await _on_turn(callback, callback_data, stores)
    if challenge is None:
        return
    if not challenge["settings"][rules.SWITCH]:
        await callback.answer(text("challenge.switch_disabled"))
        return
    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=_switch_markup(challenge))


@router.callback_query(ChallengeAction.filter(F.action == "back"))
async def back_pressed(callback: CallbackQuery, callback_data: ChallengeAction, stores: Stores) -> None:
    challenge = await _on_turn(callback, callback_data, stores)
    if challenge is None:
        return
    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=_battle_markup(challenge))


@router.callback_query(ChallengeAction.filter(F.action == "noop"))
async def empty_slot_pressed(callback: CallbackQuery) -> None:
    await callback.answer()


@router.callback_query(ChallengeAction.filter(F.action == "team"))
async def view_team_pressed(callback: CallbackQuery, callback_data: ChallengeAction, stores: Stores) -> None:
    challenge = await _in_battle(callback, callback_data, stores)
    if challenge is None:
        return
    view = await challenging.team_view(stores, challenge, callback.from_user.id)
    if view is None:
        await _ended(callback)
        return
    await callback.answer(battle_view.team_alert(view), show_alert=True)


@router.callback_query(ChallengeAction.filter(F.action == "switch"))
async def switch_pressed(callback: CallbackQuery, callback_data: ChallengeAction, stores: Stores) -> None:
    challenge = await _on_turn(callback, callback_data, stores)
    if challenge is None:
        return
    outcome = await challenging.switch(stores, challenge, int(callback_data.value))
    if outcome is None:
        await _action_lost(callback, callback_data.challenge_id, stores)
        return
    if outcome.status != challenging.SWITCHED:
        await callback.answer(text(f"challenge.{outcome.status}"), show_alert=True)
        return
    await callback.answer()
    lead = challenge_view.switch_lead(outcome)
    await _show(callback, challenge_view.screen_text(outcome.challenge, lead), _moves_markup(outcome.challenge))


async def _announce_result(bot: Bot, stores: Stores, settled: challenging.Settled) -> None:
    challenge = settled.challenge
    await _announce_moves(bot, stores, challenge, settled.gains)
    if challenge.get("message_id") is None:
        return
    try:
        await bot.edit_message_text(
            challenge_view.result_text(challenge, gains=settled.gains),
            chat_id=challenge["chat_id"],
            message_id=challenge["message_id"],
        )
    except TelegramAPIError:
        logger.info("Could not update challenge message %s", challenge["_id"])


async def finish_idle_challenges(bot: Bot, stores: Stores) -> None:
    while True:
        try:
            while (settled := await challenging.next_settled(stores)) is not None:
                await _announce_result(bot, stores, settled)
        except Exception:
            logger.exception("Could not check idle challenges")
        await asyncio.sleep(EXPIRY_CHECK_SECONDS)
