from html import escape, unescape

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message, ReplyParameters
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.game import boosts as rules
from bot.game import creatures
from bot.game.experience import STAT_NAMES
from bot.handlers.pokemon_picker import pokemon_command
from bot.services import boosts
from bot.storage.stores import Stores
from bot.ui.keyboards import EvItemAction
from bot.ui.texts import text

router = Router()

STAT_BUTTONS_PER_ROW = 3
REFUSALS = {
    boosts.NO_ITEM: "boost.no_item",
    boosts.IN_BATTLE: "hunt.already_in_battle",
    boosts.IN_TRADE: "trade.locked",
    boosts.GONE: "pokemon_picker.gone",
    boosts.FAILED: "boost.failed",
}


def _name(pokemon: dict) -> str:
    return escape(creatures.shown_name(pokemon))


def _stat_label(stat: int) -> str:
    return text(f"hunt.ev_stats.{STAT_NAMES[stat]}")


def _prompt_text(pokemon: dict) -> str:
    lines = "\n".join(
        text("boost.stat_line", stat=_stat_label(stat), ivs=pokemon["ivs"][stat])
        for stat in rules.boostable_stats(pokemon)
    )
    return text("boost.prompt", lines=lines)


def _prompt_keyboard(owner_id: int, pokemon: dict) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for stat in rules.boostable_stats(pokemon):
        builder.button(
            text=_stat_label(stat),
            callback_data=EvItemAction(owner_id=owner_id, pokemon_id=str(pokemon["_id"]), item=rules.BOOST, stat=stat),
        )
    builder.adjust(STAT_BUTTONS_PER_ROW)
    return builder.as_markup()


async def _refuse(pokemon: dict, trainer_id: int, stores: Stores) -> str | None:
    if not await boosts.owns_boost(stores, trainer_id):
        return text("boost.no_item")
    if not rules.boostable_stats(pokemon):
        return text("boost.cannot_use_any", name=_name(pokemon))
    return None


@pokemon_command("boost", code="bs", refuse=_refuse, refusal_alert=True)
async def ask_boost(message: Message, owner_id: int, pokemon: dict, quoted_id: int | None, stores: Stores) -> None:
    await message.answer(
        _prompt_text(pokemon),
        reply_parameters=(
            ReplyParameters(message_id=quoted_id, allow_sending_without_reply=True) if quoted_id else None
        ),
        reply_markup=_prompt_keyboard(owner_id, pokemon),
    )


def _refusal_text(result: boosts.BoostResult, stat: int) -> str:
    if result.status == boosts.CANNOT_USE:
        return text("boost.cannot_use", name=_name(result.pokemon), stat=_stat_label(stat))
    return text(REFUSALS[result.status])


@router.callback_query(EvItemAction.filter(F.item == rules.BOOST))
async def stat_pressed(callback: CallbackQuery, callback_data: EvItemAction, stores: Stores) -> None:
    trainer_id = callback.from_user.id
    if trainer_id != callback_data.owner_id or not isinstance(callback.message, Message):
        await callback.answer(text("common.not_your_buttons"), show_alert=True)
        return
    stat = callback_data.stat
    if not 0 <= stat < len(STAT_NAMES):
        await callback.answer()
        return
    result = await boosts.use(stores, trainer_id, callback_data.pokemon_id, stat)
    if result.status != boosts.USED:
        await callback.answer(unescape(_refusal_text(result, stat)), show_alert=True)
        return
    await callback.answer()
    await callback.message.edit_text(
        text(
            "boost.gave",
            stat=_stat_label(stat),
            name=_name(result.pokemon),
            old=result.old_value,
            new=result.new_value,
        ),
        reply_markup=None,
    )
