from html import escape, unescape

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message, ReplyParameters
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.game import creatures
from bot.game import ev_items as rules
from bot.game.experience import STAT_NAMES
from bot.handlers.cooldown import group_item_cooldown
from bot.handlers.pokemon_picker import pokemon_command
from bot.services import ev_items
from bot.storage.stores import Stores
from bot.ui.keyboards import EvItemAction
from bot.ui.texts import text

router = Router()
router.callback_query.middleware(group_item_cooldown)

STAT_BUTTONS_PER_ROW = 3
REFUSALS = {
    ev_items.IN_BATTLE: "hunt.already_in_battle",
    ev_items.IN_TRADE: "trade.locked",
    ev_items.GONE: "pokemon_picker.gone",
    ev_items.FAILED: "ev_items.failed",
}


def _name(pokemon: dict) -> str:
    return escape(creatures.shown_name(pokemon))


def _stat_label(stat: int) -> str:
    return text(f"hunt.ev_stats.{STAT_NAMES[stat]}")


def _item_name(item: str, stat: int) -> str:
    return text(f"ev_items.{item}.names.{STAT_NAMES[stat]}")


def _prompt_text(item: str) -> str:
    lines = "\n".join(
        text("ev_items.stat_line", stat=_stat_label(stat), item=_item_name(item, stat))
        for stat in range(len(STAT_NAMES))
    )
    return text(f"ev_items.{item}.prompt", lines=lines)


def _prompt_keyboard(owner_id: int, pokemon_id: str, item: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for stat in range(len(STAT_NAMES)):
        builder.button(
            text=_item_name(item, stat),
            callback_data=EvItemAction(owner_id=owner_id, pokemon_id=pokemon_id, item=item, stat=stat),
        )
    builder.adjust(STAT_BUTTONS_PER_ROW)
    return builder.as_markup()


def _again_keyboard(owner_id: int, pokemon_id: str, item: str, stat: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text=text(f"ev_items.{item}.again_button", item=_item_name(item, stat)),
        callback_data=EvItemAction(owner_id=owner_id, pokemon_id=pokemon_id, item=item, stat=stat),
    )
    return builder.as_markup()


def _no_item_text(item: str) -> str:
    return text(f"ev_items.{item}.no_item")


def _cannot_use_text(pokemon: dict, item: str, stat: int) -> str:
    return text(f"ev_items.{item}.cannot_use", name=_name(pokemon), stat=_stat_label(stat))


async def _refuse(pokemon: dict, trainer_id: int, stores: Stores, item: str) -> str | None:
    if not await ev_items.owns_item(stores, trainer_id, item):
        return _no_item_text(item)
    if not rules.can_use_on_any_stat(creatures.evs_of(pokemon), item):
        return text(f"ev_items.{item}.cannot_use_any", name=_name(pokemon))
    return None


async def _refuse_vitamin(pokemon: dict, trainer_id: int, stores: Stores) -> str | None:
    return await _refuse(pokemon, trainer_id, stores, rules.VITAMIN)


async def _refuse_berry(pokemon: dict, trainer_id: int, stores: Stores) -> str | None:
    return await _refuse(pokemon, trainer_id, stores, rules.BERRY)


async def _ask(message: Message, owner_id: int, pokemon: dict, quoted_id: int | None, item: str) -> None:
    await message.answer(
        _prompt_text(item),
        reply_parameters=(
            ReplyParameters(message_id=quoted_id, allow_sending_without_reply=True) if quoted_id else None
        ),
        reply_markup=_prompt_keyboard(owner_id, str(pokemon["_id"]), item),
    )


@pokemon_command("vitamin", code="vt", refuse=_refuse_vitamin, refusal_alert=True)
async def ask_vitamin(message: Message, owner_id: int, pokemon: dict, quoted_id: int | None, stores: Stores) -> None:
    await _ask(message, owner_id, pokemon, quoted_id, rules.VITAMIN)


@pokemon_command("berry", code="br", refuse=_refuse_berry, refusal_alert=True)
async def ask_berry(message: Message, owner_id: int, pokemon: dict, quoted_id: int | None, stores: Stores) -> None:
    await _ask(message, owner_id, pokemon, quoted_id, rules.BERRY)


def _refusal_text(result: ev_items.UseResult, item: str, stat: int) -> str:
    if result.status == ev_items.NO_ITEM:
        return _no_item_text(item)
    if result.status == ev_items.CANNOT_USE:
        return _cannot_use_text(result.pokemon, item, stat)
    return text(REFUSALS[result.status])


@router.callback_query(EvItemAction.filter(F.item.in_({rules.VITAMIN, rules.BERRY})))
async def stat_pressed(callback: CallbackQuery, callback_data: EvItemAction, stores: Stores) -> None:
    trainer_id = callback.from_user.id
    if trainer_id != callback_data.owner_id or not isinstance(callback.message, Message):
        await callback.answer(text("common.not_your_buttons"), show_alert=True)
        return
    item, stat = callback_data.item, callback_data.stat
    if not 0 <= stat < len(STAT_NAMES):
        await callback.answer()
        return
    result = await ev_items.use(stores, trainer_id, callback_data.pokemon_id, item, stat)
    if result.status != ev_items.USED:
        await callback.answer(unescape(_refusal_text(result, item, stat)), show_alert=True)
        return
    await callback.answer()
    body = text(
        f"ev_items.{item}.gave",
        item=_item_name(item, stat),
        name=_name(result.pokemon),
        stat=_stat_label(stat),
        old=result.old_value,
        new=result.new_value,
    )
    markup = _again_keyboard(trainer_id, callback_data.pokemon_id, item, stat) if result.can_use_again else None
    try:
        await callback.message.edit_text(body, reply_markup=markup)
    except TelegramBadRequest as error:
        if "message is not modified" not in str(error):
            raise
