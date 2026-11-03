import asyncio
import logging
from html import escape, unescape

from aiogram import Bot, F, Router
from aiogram.dispatcher.event.bases import SkipHandler
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.filters import CommandObject, CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message, ReplyParameters
from aiogram.utils.deep_linking import create_start_link
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.game import creatures, pokedex
from bot.handlers.cooldown import group_item_cooldown
from bot.handlers.pokemon_picker import pokemon_command
from bot.services import candy, onboarding
from bot.storage.stores import Stores
from bot.ui import tm_view
from bot.ui.keyboards import CandyGive, MovePromptAction
from bot.ui.texts import text

router = Router()
router.callback_query.middleware(group_item_cooldown)
offer_link_router = Router()
logger = logging.getLogger(__name__)

PROMPT_CHECK_SECONDS = 5
OFFER_LINK_PREFIX = "mv_"
FORGET_BUTTONS_PER_ROW = 2
REFUSALS = {
    candy.NO_CANDY: "candy.no_candy",
    candy.MAX_LEVEL: "candy.max_level",
    candy.IN_BATTLE: "hunt.already_in_battle",
    candy.IN_TRADE: "trade.locked",
    candy.GONE: "pokemon_picker.gone",
    candy.FAILED: "candy.failed",
    candy.EXPIRED: "candy.prompt_expired",
}


def _name(pokemon: dict) -> str:
    return escape(creatures.shown_name(pokemon))


def _give_keyboard(owner_id: int, pokemon_id: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=text("candy.give_button"), callback_data=CandyGive(owner_id=owner_id, pokemon_id=pokemon_id))
    return builder.as_markup()


def _prompt_button(key: str, owner_id: int, prompt_id: str, action: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(
        text=text(f"candy.{key}"),
        callback_data=MovePromptAction(owner_id=owner_id, prompt_id=prompt_id, action=action).pack(),
    )


def _prompt_keyboard(owner_id: int, prompt_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _prompt_button("teach_button", owner_id, prompt_id, "teach"),
                _prompt_button("cancel_button", owner_id, prompt_id, "cancel"),
            ]
        ]
    )


def _forget_keyboard(owner_id: int, prompt_id: str, moves: list[str]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for slot in range(len(moves)):
        builder.button(
            text=str(slot + 1),
            callback_data=MovePromptAction(owner_id=owner_id, prompt_id=prompt_id, action="forget", slot=slot),
        )
    builder.adjust(FORGET_BUTTONS_PER_ROW)
    builder.row(_prompt_button("back_button", owner_id, prompt_id, "back"))
    return builder.as_markup()


def _prompt_text(pokemon: dict, move: str) -> str:
    return text(
        "candy.learn_prompt",
        level=pokemon["level"],
        name=_name(pokemon),
        move=pokedex.display_name(move),
        card=tm_view.move_text(move),
    )


def _forget_text(pokemon: dict, move: str) -> str:
    return tm_view.forget_text(pokemon, move)


def _gave_text(result: candy.CandyResult) -> str:
    name = _name(result.pokemon)
    lines = [
        text("candy.gave", name=name),
        text("candy.levels", old=result.old_level, new=result.new_level),
    ]
    lines.extend(text("candy.learned", name=name, move=pokedex.display_name(move)) for move in result.learned)
    if result.ready:
        lines.append(text("candy.ready", name=name))
    return "\n".join(lines)


async def _is_owner(callback: CallbackQuery, owner_id: int) -> bool:
    if callback.from_user.id == owner_id and isinstance(callback.message, Message):
        return True
    await callback.answer(text("common.not_your_buttons"), show_alert=True)
    return False


async def _edit(message: Message, body: str, markup=None) -> None:
    try:
        await message.edit_text(body, reply_markup=markup)
    except TelegramBadRequest as error:
        if "message is not modified" not in str(error):
            raise


async def offer_move(
    bot: Bot,
    stores: Stores,
    trainer_id: int,
    trainer_name: str,
    chat_id: int,
    pokemon: dict,
    new_level: int,
    move: str,
) -> None:
    shown = {**pokemon, "level": new_level}
    prompt_id = candy.new_prompt_id()
    try:
        sent = await bot.send_message(
            trainer_id,
            _prompt_text(shown, move),
            reply_markup=_prompt_keyboard(trainer_id, prompt_id),
        )
    except TelegramAPIError as error:
        logger.warning("Could not send move prompt: %s", error)
        return
    await candy.remember_prompt(stores, trainer_id, prompt_id, str(pokemon["_id"]), move, sent.chat.id, sent.message_id)
    if chat_id == trainer_id:
        return
    link = await create_start_link(bot, f"{OFFER_LINK_PREFIX}{prompt_id}")
    try:
        await bot.send_message(
            chat_id,
            text(
                "candy.group_notice",
                trainer_id=trainer_id,
                trainer=escape(trainer_name),
                name=_name(pokemon),
            ),
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text=text("candy.go_button"), url=link)]]
            ),
        )
    except TelegramAPIError as error:
        logger.warning("Could not send move notice: %s", error)


@offer_link_router.message(CommandStart(deep_link=True, magic=F.args.startswith(OFFER_LINK_PREFIX)), F.from_user)
async def offer_link_opened(message: Message, command: CommandObject, stores: Stores) -> None:
    if not await onboarding.has_started(stores, message.from_user.id):
        raise SkipHandler
    prompt_id = command.args.removeprefix(OFFER_LINK_PREFIX)
    if await candy.prompt_view(stores, message.from_user.id, prompt_id) is None:
        await message.answer(text("candy.prompt_expired"))


async def _refuse_max_level(pokemon: dict, trainer_id: int, stores: Stores) -> str | None:
    return text("candy.max_level", name=_name(pokemon)) if candy.at_max_level(pokemon) else None


@pokemon_command("candy", code="cd", refuse=_refuse_max_level)
async def ask_to_give(
    message: Message,
    owner_id: int,
    pokemon: dict,
    quoted_id: int | None,
    stores: Stores,
) -> None:
    await message.answer(
        text("candy.ask"),
        reply_parameters=(
            ReplyParameters(message_id=quoted_id, allow_sending_without_reply=True) if quoted_id else None
        ),
        reply_markup=_give_keyboard(owner_id, str(pokemon["_id"])),
    )


@router.callback_query(CandyGive.filter())
async def give_pressed(callback: CallbackQuery, callback_data: CandyGive, stores: Stores) -> None:
    if not await _is_owner(callback, callback_data.owner_id):
        return
    result = await candy.give(stores, callback.from_user.id, callback_data.pokemon_id)
    if result.status != candy.GAVE:
        name = _name(result.pokemon) if result.pokemon else ""
        await callback.answer(unescape(text(REFUSALS[result.status], name=name)), show_alert=True)
        return
    await callback.answer()
    markup = _give_keyboard(callback.from_user.id, callback_data.pokemon_id) if candy.can_take_more(result) else None
    await _edit(callback.message, _gave_text(result), markup)
    for move in result.waiting:
        await offer_move(
            callback.bot,
            stores,
            callback.from_user.id,
            callback.from_user.first_name,
            callback.message.chat.id,
            result.pokemon,
            result.new_level,
            move,
        )


@router.callback_query(MovePromptAction.filter(F.action == "back"))
async def prompt_back(callback: CallbackQuery, callback_data: MovePromptAction, stores: Stores) -> None:
    if not await _is_owner(callback, callback_data.owner_id):
        return
    view = await candy.prompt_view(stores, callback.from_user.id, callback_data.prompt_id)
    if view is None:
        await callback.answer(text("candy.prompt_expired"), show_alert=True)
        return
    await callback.answer()
    await _edit(
        callback.message,
        _prompt_text(view.pokemon, view.prompt["move"]),
        _prompt_keyboard(callback.from_user.id, callback_data.prompt_id),
    )


@router.callback_query(MovePromptAction.filter(F.action == "cancel"))
async def prompt_cancelled(callback: CallbackQuery, callback_data: MovePromptAction, stores: Stores) -> None:
    if not await _is_owner(callback, callback_data.owner_id):
        return
    result = await candy.decline(stores, callback.from_user.id, callback_data.prompt_id)
    if result.status == candy.EXPIRED:
        await callback.answer(text("candy.prompt_expired"), show_alert=True)
        return
    await callback.answer()
    await _edit(callback.message, _not_learned_text(result.pokemon, result.move))


def _not_learned_text(pokemon: dict | None, move: str) -> str:
    name = _name(pokemon) if pokemon else text("candy.unknown_pokemon")
    return text("candy.not_learned", name=name, move=pokedex.display_name(move))


@router.callback_query(MovePromptAction.filter(F.action.in_({"teach", "forget"})))
async def prompt_teach(callback: CallbackQuery, callback_data: MovePromptAction, stores: Stores) -> None:
    if not await _is_owner(callback, callback_data.owner_id):
        return
    trainer_id = callback.from_user.id
    forgotten = callback_data.slot if callback_data.action == "forget" else None
    result = await candy.learn(stores, trainer_id, callback_data.prompt_id, forgotten)
    if result.status == candy.NEEDS_FORGET:
        await callback.answer()
        await _edit(
            callback.message,
            _forget_text(result.pokemon, result.move),
            _forget_keyboard(trainer_id, callback_data.prompt_id, result.pokemon["moves"]),
        )
        return
    if result.status != candy.LEARNED:
        await callback.answer(text(REFUSALS[result.status], name=""), show_alert=True)
        return
    await callback.answer()
    move = pokedex.display_name(result.move)
    if result.forgotten is None:
        body = text("tm.learned", name=_name(result.pokemon), move=move)
    else:
        body = text(
            "tm.learned_forgot",
            name=_name(result.pokemon),
            move=move,
            forgotten=pokedex.display_name(result.forgotten),
        )
    await _edit(callback.message, body)


async def expire_move_prompts(bot: Bot, stores: Stores) -> None:
    while True:
        try:
            while (expired := await candy.next_expired_prompts(stores)) is not None:
                for prompt, pokemon in expired:
                    try:
                        await bot.edit_message_text(
                            text=_not_learned_text(pokemon, prompt["move"]),
                            reply_markup=None,
                            **prompt["message"],
                        )
                    except TelegramAPIError as error:
                        logger.warning("Could not announce expired move prompt: %s", error)
        except Exception:
            logger.exception("Could not check expired move prompts")
        await asyncio.sleep(PROMPT_CHECK_SECONDS)
