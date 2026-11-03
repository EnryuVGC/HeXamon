from typing import ClassVar

from aiogram.filters.callback_data import CallbackData
from aiogram.types import (
    ForceReply,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.data import catalog
from bot.game.experience import STAT_NAMES
from bot.game import pokedex
from bot.game import pokedex_entries as entries
from bot.game.card_styles import AVATAR, CHOICES, TEMPLATE, TEXT, TEXT_BUTTONS
from bot.game.catching import THROWABLE_BALLS
from bot.game.challenges import (
    FORM_CHANGES,
    LEVELS_PER_RANGE,
    MAX_LEGENDARIES,
    MAX_LEVEL,
    MAX_POKEMON,
    MIN_LEGENDARIES,
    MIN_LEVEL,
    RANDOM,
    SANDBOX,
    SETTING_VALUES,
    SWITCH,
    TOGGLE_SETTINGS,
    level_ranges,
)
from bot.game.display import OPTIONS as DISPLAY_OPTIONS
from bot.game.form_changes import FormOption
from bot.game.inventory import stone_name
from bot.game.lottery import HIGHEST_NUMBER, MULTIPLIER_FEE, NO_PICKS, encode_picks
from bot.game.paging import PAGE_SIZE_OPTIONS, available_jumps
from bot.game.pokedex_list import JUMP_SIZES as POKEDEX_JUMP_SIZES
from bot.game.sorting import OPTIONS as SORT_OPTIONS
from bot.game.stats_pages import STATS_PAGES
from bot.game.teams import TEAM_SIZE, team_numbers
from bot.ui import pokemon_list
from bot.ui.texts import text


TEAM_ADD_SCREEN = "ta"
COLLECTION_SCREEN = "mp"
TRADE_SCREEN = "tr"
INVENTORY_MAIN = "main"
INVENTORY_KEY_ITEMS = "key"
INVENTORY_TMS = "tms"
STORE_ITEMS = "items"
STORE_BALLS = "balls"
STORE_TMS = "tms"
TM_SCREEN_PREFIX = "tm"
TM_USE = "use"
TM_SELL = "sell"
TM_CONFIRM_SELL = "sold"
TM_CANCEL = "cancel"
TM_BUY = "buy"
TM_BACK = "back"
TM_PICK = "pick"
TM_FORGET = "forget"
TM_LEARNERS_BACK = "list"
SORT_BUTTONS_PER_ROW = 6
DISPLAY_BUTTONS_PER_ROW = 5
LOTTERY_PLAY = "play"
LOTTERY_COUNTDOWN = "time"
LOTTERY_NUMBER = "num"
LOTTERY_MULTIPLIER = "mult"
LOTTERY_RANDOM = "rand"
LOTTERY_CLEAR = "clear"
LOTTERY_SAVE = "save"
LOTTERY_ENTRIES = "list"
LOTTERY_NUMBERS_PER_ROW = 5


class FirstPartnerChoice(CallbackData, prefix="partner"):
    owner_id: int
    dex_id: int


class FirstPartnerNone(CallbackData, prefix="partnern"):
    owner_id: int
    confirming: bool


class LotteryAction(CallbackData, prefix="lot"):
    action: str
    number: int = 0
    picks: str = NO_PICKS
    multiplied: bool = False


def lottery_menu_keyboard(has_entries: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=text("lottery.play_button"), callback_data=LotteryAction(action=LOTTERY_PLAY))
    builder.button(text=text("lottery.countdown_button"), callback_data=LotteryAction(action=LOTTERY_COUNTDOWN))
    if has_entries:
        builder.button(text=text("lottery.entries_button"), callback_data=LotteryAction(action=LOTTERY_ENTRIES))
    builder.adjust(2, 1)
    return builder.as_markup()


def lottery_picker_keyboard(picks: list[int], multiplied: bool) -> InlineKeyboardMarkup:
    encoded = encode_picks(picks)
    builder = InlineKeyboardBuilder()
    for number in range(1, HIGHEST_NUMBER + 1):
        builder.button(
            text=text("lottery.number_picked", number=number) if number in picks else str(number),
            callback_data=LotteryAction(action=LOTTERY_NUMBER, number=number, picks=encoded, multiplied=multiplied),
        )
    mark = text("lottery.mark_on" if multiplied else "lottery.mark_off")
    builder.button(
        text=text("lottery.multiplier_button", mark=mark, fee=MULTIPLIER_FEE),
        callback_data=LotteryAction(action=LOTTERY_MULTIPLIER, picks=encoded, multiplied=multiplied),
    )
    for label_key, action in (
        ("lottery.random_button", LOTTERY_RANDOM),
        ("lottery.clear_button", LOTTERY_CLEAR),
        ("lottery.save_button", LOTTERY_SAVE),
    ):
        builder.button(
            text=text(label_key),
            callback_data=LotteryAction(action=action, picks=encoded, multiplied=multiplied),
        )
    rows = HIGHEST_NUMBER // LOTTERY_NUMBERS_PER_ROW
    builder.adjust(*[LOTTERY_NUMBERS_PER_ROW] * rows, 1, 3)
    return builder.as_markup()


def lottery_saved_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=text("lottery.entries_button"), callback_data=LotteryAction(action=LOTTERY_ENTRIES))
    return builder.as_markup()


class HuntAction(CallbackData, prefix="hunt"):
    owner_id: int
    encounter_id: str
    action: str
    value: str = "-"


class EvTrainingAction(CallbackData, prefix="evt"):
    owner_id: int
    stat: str = ""


class NicknameChoice(CallbackData, prefix="nick"):
    owner_id: int
    pokemon_id: str


class SortAction(CallbackData, prefix="sort"):
    CHANGE_DIRECTION: ClassVar[str] = "direction"

    owner_id: int
    key: str


def sort_keyboard(owner_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for number, option in enumerate(SORT_OPTIONS, start=1):
        builder.button(text=str(number), callback_data=SortAction(owner_id=owner_id, key=option.key))
    builder.adjust(SORT_BUTTONS_PER_ROW)
    builder.row(
        InlineKeyboardButton(
            text=text("sort.change_direction_button"),
            callback_data=SortAction(owner_id=owner_id, key=SortAction.CHANGE_DIRECTION).pack(),
        )
    )
    return builder.as_markup()


class DisplayAction(CallbackData, prefix="display"):
    TOGGLE_NUMBERS: ClassVar[str] = "numbers"

    owner_id: int
    key: str


def display_keyboard(owner_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for number, key in enumerate(DISPLAY_OPTIONS, start=1):
        builder.button(text=str(number), callback_data=DisplayAction(owner_id=owner_id, key=key))
    builder.adjust(DISPLAY_BUTTONS_PER_ROW)
    builder.row(
        InlineKeyboardButton(
            text=text("display.toggle_numbers_button"),
            callback_data=DisplayAction(owner_id=owner_id, key=DisplayAction.TOGGLE_NUMBERS).pack(),
        )
    )
    return builder.as_markup()


class PageSizeAction(CallbackData, prefix="psize"):
    owner_id: int
    size: int


def page_size_keyboard(owner_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for size in PAGE_SIZE_OPTIONS:
        builder.button(text=str(size), callback_data=PageSizeAction(owner_id=owner_id, size=size))
    builder.adjust(len(PAGE_SIZE_OPTIONS))
    return builder.as_markup()


class TeamAction(CallbackData, prefix="team"):
    owner_id: int
    action: str
    value: str = "-"


def _team_button(builder: InlineKeyboardBuilder, label: str, owner_id: int, action: str, value: str = "-") -> None:
    builder.button(text=label, callback_data=TeamAction(owner_id=owner_id, action=action, value=value))


def team_keyboard(owner_id: int, edit_link: str | None = None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for number in team_numbers():
        _team_button(builder, text("team.team_button", number=number), owner_id, "view", str(number))
    if edit_link:
        builder.button(text=text("team.edit_button"), url=edit_link)
    else:
        _team_button(builder, text("team.edit_button"), owner_id, "edit")
    builder.adjust(2, 2, 2, 1)
    return builder.as_markup()


def editor_keyboard(owner_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    _team_button(builder, text("team.add_button"), owner_id, "add")
    _team_button(builder, text("team.remove_button"), owner_id, "remove")
    _team_button(builder, text("team.order_button"), owner_id, "order")
    _team_button(builder, text("team.randomize_button"), owner_id, "shuffle")
    for number in team_numbers():
        _team_button(builder, text("team.save_button", number=number), owner_id, "save", str(number))
    builder.adjust(2)
    return builder.as_markup()


def add_keyboard(owner_id: int, page) -> InlineKeyboardMarkup:
    return pokemon_list.keyboard(
        owner_id,
        TEAM_ADD_SCREEN,
        page,
        pick_callback=lambda pokemon: TeamAction(
            owner_id=owner_id,
            action="pick",
            value=str(pokemon["_id"]),
        ).pack(),
        extra_rows=[[_editor_back(owner_id)]],
    )


def _editor_back(owner_id: int) -> InlineKeyboardButton:
    return InlineKeyboardButton(
        text=text("hunt.back_button"),
        callback_data=TeamAction(owner_id=owner_id, action="edit").pack(),
    )


def remove_keyboard(owner_id: int, member_ids: list[str]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for number, member_id in enumerate(member_ids, start=1):
        _team_button(builder, str(number), owner_id, "drop", member_id)
    builder.adjust(4)
    builder.row(_editor_back(owner_id))
    return builder.as_markup()


def replace_keyboard(owner_id: int, pokemon_id: str, size: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for slot in range(size):
        _team_button(builder, str(slot + 1), owner_id, "replace", f"{pokemon_id}.{slot}")
    builder.adjust(4)
    builder.row(
        InlineKeyboardButton(
            text=text("hunt.back_button"),
            callback_data=TeamAction(owner_id=owner_id, action="add").pack(),
        )
    )
    return builder.as_markup()


def order_keyboard(owner_id: int, size: int, chosen: int | None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for slot in range(size):
        if slot == chosen:
            continue
        if chosen is None:
            _team_button(builder, str(slot + 1), owner_id, "first", str(slot))
        else:
            _team_button(builder, str(slot + 1), owner_id, "second", f"{chosen}.{slot}")
    builder.adjust(4)
    builder.row(_editor_back(owner_id))
    return builder.as_markup()


class StatsPage(CallbackData, prefix="stats"):
    owner_id: int
    pokemon_id: str
    page: str


class StatsOpen(CallbackData, prefix="statso"):
    owner_id: int
    pokemon_id: str


def stats_keyboard(owner_id: int, pokemon_id: str, current_page: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for page in STATS_PAGES:
        if page != current_page:
            builder.button(
                text=text(f"stats.{page}_button"),
                callback_data=StatsPage(owner_id=owner_id, pokemon_id=pokemon_id, page=page),
            )
    builder.adjust(len(STATS_PAGES) - 1)
    return builder.as_markup()


def first_partner_keyboard(owner_id: int, partners: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for partner in partners:
        builder.button(
            text=partner.name,
            callback_data=FirstPartnerChoice(owner_id=owner_id, dex_id=partner.dex_id),
        )
    builder.button(
        text=text("start.none_button"),
        callback_data=FirstPartnerNone(owner_id=owner_id, confirming=True),
    )
    builder.adjust(len(partners), 1)
    return builder.as_markup()


def fallback_partner_keyboard(owner_id: int, fallback_partner) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text=text("start.none_yes_button"),
        callback_data=FirstPartnerChoice(owner_id=owner_id, dex_id=fallback_partner.dex_id),
    )
    builder.button(
        text=text("start.none_back_button"),
        callback_data=FirstPartnerNone(owner_id=owner_id, confirming=False),
    )
    builder.adjust(2)
    return builder.as_markup()


def open_private_chat_keyboard(link: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=text("common.open_bot_button"), url=link)
    return builder.as_markup()


def main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=text("start.hunt_button"))]],
        resize_keyboard=True,
    )


def close_keyboard() -> ReplyKeyboardRemove:
    return ReplyKeyboardRemove(remove_keyboard=True, selective=True)


def nickname_reply_prompt(selective: bool = False) -> ForceReply:
    return ForceReply(force_reply=True, selective=selective)


def appeared_keyboard(owner_id: int, encounter_id: str, dex_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text=text("hunt.battle_button"),
        callback_data=HuntAction(owner_id=owner_id, encounter_id=encounter_id, action="battle", value=str(dex_id)),
    )
    builder.button(
        text=text("hunt.ev_yield_button"),
        callback_data=HuntAction(owner_id=owner_id, encounter_id=encounter_id, action="ev", value=str(dex_id)),
    )
    builder.adjust(2)
    return builder.as_markup()


def expert_appeared_keyboard(owner_id: int, encounter_id: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text=text("hunt.battle_button"),
        callback_data=HuntAction(owner_id=owner_id, encounter_id=encounter_id, action="expert"),
    )
    return builder.as_markup()


def safari_appeared_keyboard(owner_id: int, encounter_id: str, dex_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text=text("safari.catch_button"),
        callback_data=HuntAction(owner_id=owner_id, encounter_id=encounter_id, action="safari_catch"),
    )
    builder.button(
        text=text("hunt.ev_yield_button"),
        callback_data=HuntAction(owner_id=owner_id, encounter_id=encounter_id, action="ev", value=str(dex_id)),
    )
    builder.adjust(2)
    return builder.as_markup()


def ev_training_begin_keyboard(owner_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=text("ev_training.begin_button"), callback_data=EvTrainingAction(owner_id=owner_id))
    return builder.as_markup()


def ev_training_zone_keyboard(owner_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for stat in STAT_NAMES:
        builder.button(text=text(f"ev_training.zones.{stat}"), callback_data=EvTrainingAction(owner_id=owner_id, stat=stat))
    builder.adjust(2)
    return builder.as_markup()


def ev_training_appeared_keyboard(owner_id: int, encounter_id: str, dex_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text=text("hunt.battle_button"),
        callback_data=HuntAction(owner_id=owner_id, encounter_id=encounter_id, action="battle", value=str(dex_id)),
    )
    return builder.as_markup()


def safari_action_keyboard(owner_id: int, encounter_id: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text=text("safari.throw_button"),
        callback_data=HuntAction(owner_id=owner_id, encounter_id=encounter_id, action="safari_throw"),
    )
    builder.button(
        text=text("safari.run_button"),
        callback_data=HuntAction(owner_id=owner_id, encounter_id=encounter_id, action="run"),
    )
    builder.adjust(2)
    return builder.as_markup()


def battle_keyboard(
    owner_id: int,
    encounter_id: str,
    moves: list[str],
    form_options: list[FormOption] | None = None,
    catchable: bool = True,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for index, name in enumerate(moves):
        builder.button(
            text=pokedex.display_name(name),
            callback_data=HuntAction(
                owner_id=owner_id,
                encounter_id=encounter_id,
                action="move",
                value=str(index),
            ),
        )
    builder.adjust(2)
    if form_options:
        builder.row(
            *(
                InlineKeyboardButton(
                    text=stone_name(option.item),
                    callback_data=HuntAction(
                        owner_id=owner_id,
                        encounter_id=encounter_id,
                        action="form",
                        value=str(option.form_id),
                    ).pack(),
                )
                for option in form_options
            )
        )
    ball_label = "hunt.poke_ball_button" if catchable else "challenge.balls_button"
    builder.row(
        _hunt_button(ball_label, owner_id, encounter_id, "balls"),
        _hunt_button("hunt.run_button", owner_id, encounter_id, "run"),
        _hunt_button("hunt.pokemons_button", owner_id, encounter_id, "pokemons"),
    )
    return builder.as_markup()


def _hunt_button(label_key: str, owner_id: int, encounter_id: str, action: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(
        text=text(label_key),
        callback_data=HuntAction(owner_id=owner_id, encounter_id=encounter_id, action=action).pack(),
    )


def switch_keyboard(
    owner_id: int,
    encounter_id: str,
    team_ids: list[str],
    active_id: str | None,
    fainted_ids: list[str],
    can_go_back: bool,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for slot in range(TEAM_SIZE):
        if slot < len(team_ids) and team_ids[slot] != active_id and team_ids[slot] not in fainted_ids:
            builder.button(
                text=str(slot + 1),
                callback_data=HuntAction(
                    owner_id=owner_id,
                    encounter_id=encounter_id,
                    action="switch",
                    value=str(slot),
                ),
            )
        else:
            builder.button(
                text=text("hunt.empty_slot"),
                callback_data=HuntAction(owner_id=owner_id, encounter_id=encounter_id, action="noop"),
            )
    builder.adjust(2)
    builder.row(_hunt_button("hunt.view_team_button", owner_id, encounter_id, "team"))
    if can_go_back:
        builder.row(_hunt_button("hunt.back_button", owner_id, encounter_id, "back"))
    return builder.as_markup()


def ball_keyboard(owner_id: int, encounter_id: str, balls: dict) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for ball in THROWABLE_BALLS:
        count = balls.get(ball, 0)
        if count > 0:
            builder.button(
                text=text(f"hunt.ball_{ball}", count=count),
                callback_data=HuntAction(
                    owner_id=owner_id,
                    encounter_id=encounter_id,
                    action="throw",
                    value=ball,
                ),
            )
    builder.adjust(3)
    builder.row(
        InlineKeyboardButton(
            text=text("hunt.back_button"),
            callback_data=HuntAction(owner_id=owner_id, encounter_id=encounter_id, action="back").pack(),
        )
    )
    return builder.as_markup()


class PokedexPage(CallbackData, prefix="dxp"):
    owner_id: int
    dex_id: int
    view: str
    turned: bool = False


def pokedex_page_keyboard(owner_id: int, dex_id: int, view: str) -> InlineKeyboardMarkup:
    forms = entries.forms_of(dex_id)
    index = forms.index(dex_id)
    view_row = [
        InlineKeyboardButton(
            text=text(f"pokedex.view_buttons.{other}"),
            callback_data=PokedexPage(owner_id=owner_id, dex_id=dex_id, view=other).pack(),
        )
        for other in entries.VIEWS
        if other != view
    ]
    nav = pokemon_list.page_rows(
        index + 1,
        len(forms),
        [],
        InlineKeyboardButton(
            text=text("pokemon_list.page_indicator", page=index + 1, pages=len(forms)),
            callback_data=pokemon_list.PokemonListIndicator(owner_id=owner_id).pack(),
        ),
        lambda label_key, delta: InlineKeyboardButton(
            text=text(f"pokemon_list.{label_key}"),
            callback_data=PokedexPage(owner_id=owner_id, dex_id=forms[index + delta], view=view, turned=True).pack(),
        ),
    )
    return InlineKeyboardMarkup(inline_keyboard=[view_row, *nav])


class PokedexSuggestion(CallbackData, prefix="dxs"):
    owner_id: int
    dex_id: int
    accepted: bool


def pokedex_suggestion_keyboard(owner_id: int, dex_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for label_key, accepted in (("pokemon_picker.yes_button", True), ("pokemon_picker.no_button", False)):
        builder.button(
            text=text(label_key),
            callback_data=PokedexSuggestion(owner_id=owner_id, dex_id=dex_id, accepted=accepted),
        )
    builder.adjust(2)
    return builder.as_markup()


class PokedexEntry(CallbackData, prefix="dex"):
    dex_id: int


class PokedexPageTurn(CallbackData, prefix="dexp"):
    owner_id: int
    page: int


def _pokedex_nav_button(label_key: str, owner_id: int, target: int) -> InlineKeyboardButton:
    return InlineKeyboardButton(
        text=text(f"pokemon_list.{label_key}"),
        callback_data=PokedexPageTurn(owner_id=owner_id, page=target).pack(),
    )


def pokedex_keyboard(owner_id: int, page: int, pages: int) -> InlineKeyboardMarkup:
    rows = pokemon_list.page_rows(
        page,
        pages,
        available_jumps(pages, POKEDEX_JUMP_SIZES),
        InlineKeyboardButton(
            text=text("pokemon_list.page_indicator", page=page, pages=pages),
            callback_data=pokemon_list.PokemonListIndicator(owner_id=owner_id).pack(),
        ),
        lambda label_key, delta: _pokedex_nav_button(label_key, owner_id, page + delta),
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


class TradeAction(CallbackData, prefix="tr"):
    trade_id: str
    action: str
    value: str = "-"


def trade_request_keyboard(trade_id: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=text("trade.agree_button"), callback_data=TradeAction(trade_id=trade_id, action="agree"))
    return builder.as_markup()


def trade_pick_keyboard(owner_id: int, trade_id: str, page) -> InlineKeyboardMarkup:
    return pokemon_list.keyboard(
        owner_id,
        TRADE_SCREEN,
        page,
        pick_callback=lambda pokemon: TradeAction(
            trade_id=trade_id,
            action="pick",
            value=str(pokemon["_id"]),
        ).pack(),
    )


def trade_confirm_keyboard(trade_id: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=text("trade.accept_button"), callback_data=TradeAction(trade_id=trade_id, action="accept"))
    builder.button(text=text("trade.cancel_button"), callback_data=TradeAction(trade_id=trade_id, action="cancel"))
    builder.adjust(2)
    return builder.as_markup()


class ChallengeAction(CallbackData, prefix="ch"):
    challenge_id: str
    action: str
    value: str = "-"


def _challenge_button(label_key: str, challenge_id: str, action: str, value: str = "-") -> InlineKeyboardButton:
    return InlineKeyboardButton(
        text=text(label_key),
        callback_data=ChallengeAction(challenge_id=challenge_id, action=action, value=value).pack(),
    )


def challenge_prompt_keyboard(challenge_id: str, edit_link: str, anyone_ready: bool) -> InlineKeyboardMarkup:
    ready_label = "challenge.ready_button_on" if anyone_ready else "challenge.ready_button"
    builder = InlineKeyboardBuilder()
    builder.row(
        _challenge_button(ready_label, challenge_id, "ready"),
        _challenge_button("challenge.settings_button", challenge_id, "settings"),
    )
    builder.row(InlineKeyboardButton(text=text("challenge.edit_team_button"), url=edit_link))
    return builder.as_markup()


def _setting_button(name: str, challenge_id: str) -> InlineKeyboardButton:
    action = "toggle" if name in TOGGLE_SETTINGS else "choose"
    return _challenge_button(f"challenge.setting_buttons.{name}", challenge_id, action, name)


def challenge_settings_keyboard(challenge_id: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for left, right in (
        (MAX_POKEMON, SWITCH),
        (MIN_LEGENDARIES, MAX_LEGENDARIES),
        (MIN_LEVEL, MAX_LEVEL),
        (FORM_CHANGES, SANDBOX),
    ):
        builder.row(_setting_button(left, challenge_id), _setting_button(right, challenge_id))
    builder.row(_setting_button(RANDOM, challenge_id))
    builder.row(
        _challenge_button("challenge.save_button", challenge_id, "save"),
        _challenge_button("challenge.back_button", challenge_id, "prompt"),
    )
    return builder.as_markup()


def _setting_value_buttons(challenge_id: str, name: str, values, per_row: int, back_action: str, back_value: str):
    builder = InlineKeyboardBuilder()
    for value in values:
        builder.button(
            text=str(value),
            callback_data=ChallengeAction(challenge_id=challenge_id, action="set", value=f"{name}={value}"),
        )
    builder.adjust(per_row)
    builder.row(_challenge_button("challenge.back_button", challenge_id, back_action, back_value))
    return builder.as_markup()


def challenge_number_keyboard(challenge_id: str, name: str) -> InlineKeyboardMarkup:
    return _setting_value_buttons(challenge_id, name, SETTING_VALUES[name], 3, "settings", "-")


def challenge_level_ranges_keyboard(challenge_id: str, name: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for start, end in level_ranges():
        builder.button(
            text=text("challenge.level_range", start=start, end=end),
            callback_data=ChallengeAction(challenge_id=challenge_id, action="range", value=f"{name}={start}"),
        )
    builder.adjust(2)
    builder.row(_challenge_button("challenge.back_button", challenge_id, "settings"))
    return builder.as_markup()


def challenge_levels_keyboard(challenge_id: str, name: str, start: int) -> InlineKeyboardMarkup:
    levels = range(start, start + LEVELS_PER_RANGE)
    return _setting_value_buttons(challenge_id, name, levels, 5, "choose", name)


def challenge_battle_keyboard(
    challenge_id: str,
    moves: list[str],
    form_options: list[FormOption] | None = None,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for index, name in enumerate(moves):
        builder.button(
            text=pokedex.display_name(name),
            callback_data=ChallengeAction(challenge_id=challenge_id, action="move", value=str(index)),
        )
    builder.adjust(2)
    if form_options:
        builder.row(
            *(
                InlineKeyboardButton(
                    text=stone_name(option.item),
                    callback_data=ChallengeAction(
                        challenge_id=challenge_id,
                        action="form",
                        value=str(option.form_id),
                    ).pack(),
                )
                for option in form_options
            )
        )
    builder.row(
        _challenge_button("challenge.balls_button", challenge_id, "balls"),
        _challenge_button("challenge.run_button", challenge_id, "run"),
        _challenge_button("challenge.pokemon_button", challenge_id, "pokemon"),
    )
    return builder.as_markup()


def challenge_switch_keyboard(challenge_id: str, team: list[dict], can_go_back: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for slot in range(TEAM_SIZE):
        if slot < len(team) and team[slot]["hp"] > 0:
            builder.button(
                text=str(slot + 1),
                callback_data=ChallengeAction(challenge_id=challenge_id, action="switch", value=str(slot)),
            )
        else:
            builder.button(
                text=text("hunt.empty_slot"),
                callback_data=ChallengeAction(challenge_id=challenge_id, action="noop"),
            )
    builder.adjust(2)
    builder.row(_challenge_button("challenge.view_team_button", challenge_id, "team"))
    if can_go_back:
        builder.row(_challenge_button("challenge.back_button", challenge_id, "back"))
    return builder.as_markup()


class MoreStats(CallbackData, prefix="mst"):
    owner_id: int


def more_stats_keyboard(owner_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=text("mystats.more_button"), callback_data=MoreStats(owner_id=owner_id))
    return builder.as_markup()


class TravelChoice(CallbackData, prefix="trv"):
    owner_id: int
    region: int


TRAVEL_BUTTONS_PER_ROW = 4


def travel_keyboard(owner_id: int, region_count: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for index in range(region_count):
        builder.button(text=str(index + 1), callback_data=TravelChoice(owner_id=owner_id, region=index))
    builder.adjust(TRAVEL_BUTTONS_PER_ROW)
    return builder.as_markup()


class CardAction(CallbackData, prefix="crd"):
    owner_id: int
    action: str
    field: str = ""
    value: int = 0


CARD_FIELDS = (TEMPLATE, TEXT, AVATAR)
CARD_BUTTONS_PER_ROW = 5
CARD_TEMPLATE_BUTTONS_PER_ROW = 4


def card_main_keyboard(owner_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for field in CARD_FIELDS:
        builder.button(text=text(f"card.{field}_button"), callback_data=CardAction(owner_id=owner_id, action="open", field=field))
    builder.adjust(len(CARD_FIELDS))
    return builder.as_markup()


def card_template_keyboard(owner_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for value in range(1, CHOICES[TEMPLATE] + 1):
        builder.button(text=str(value), callback_data=CardAction(owner_id=owner_id, action="save", field=TEMPLATE, value=value))
    builder.adjust(CARD_TEMPLATE_BUTTONS_PER_ROW)
    return builder.as_markup()


def card_text_keyboard(owner_id: int) -> InlineKeyboardMarkup:
    colors = catalog.load("card_text_colors")
    builder = InlineKeyboardBuilder()
    for value in TEXT_BUTTONS:
        builder.button(text=colors[value - 1]["name"], callback_data=CardAction(owner_id=owner_id, action="save", field=TEXT, value=value))
    builder.adjust(CARD_TEMPLATE_BUTTONS_PER_ROW)
    return builder.as_markup()


def card_options_keyboard(owner_id: int, field: str, chosen: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for value in range(1, CHOICES[field] + 1):
        selected = value == chosen
        builder.button(
            text=text("card.selected", value=value) if selected else str(value),
            callback_data=CardAction(owner_id=owner_id, action="keep" if selected else "pick", field=field, value=value),
        )
    builder.adjust(CARD_BUTTONS_PER_ROW)
    builder.row(
        InlineKeyboardButton(
            text=text("card.save_button"),
            callback_data=CardAction(owner_id=owner_id, action="save", field=field, value=chosen).pack(),
        ),
        InlineKeyboardButton(
            text=text("card.back_button"),
            callback_data=CardAction(owner_id=owner_id, action="back").pack(),
        ),
    )
    return builder.as_markup()


class EvItemAction(CallbackData, prefix="evi"):
    owner_id: int
    pokemon_id: str
    item: str
    stat: int


class CandyGive(CallbackData, prefix="candy"):
    owner_id: int
    pokemon_id: str


class MovePromptAction(CallbackData, prefix="mvp"):
    owner_id: int
    prompt_id: str
    action: str
    slot: int = 0


class EvolveAction(CallbackData, prefix="evo"):
    owner_id: int
    pokemon_id: str
    dex_id: int
    action: str


def evolve_keyboard(owner_id: int, pokemon_id: str, dex_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for label_key, action in (("evolve.confirm_button", "yes"), ("evolve.cancel_button", "no")):
        builder.button(
            text=text(label_key),
            callback_data=EvolveAction(owner_id=owner_id, pokemon_id=pokemon_id, dex_id=dex_id, action=action),
        )
    builder.adjust(2)
    return builder.as_markup()


class TmAction(CallbackData, prefix="tm"):
    owner_id: int
    number: int
    action: str
    pokemon_id: str = "-"
    slot: int = 0


class StorePage(CallbackData, prefix="store"):
    owner_id: int
    page: str


def _store_button(page: str, owner_id: int) -> InlineKeyboardButton:
    return InlineKeyboardButton(
        text=text(f"shop.{page}_button"),
        callback_data=StorePage(owner_id=owner_id, page=page).pack(),
    )


def store_keyboard(owner_id: int, page: str = STORE_ITEMS) -> InlineKeyboardMarkup:
    pages = {
        STORE_ITEMS: (STORE_BALLS, STORE_TMS),
        STORE_BALLS: (STORE_ITEMS, STORE_TMS),
        STORE_TMS: (STORE_BALLS, STORE_ITEMS),
    }[page]
    return InlineKeyboardMarkup(inline_keyboard=[[_store_button(other, owner_id) for other in pages]])


class InventoryPage(CallbackData, prefix="inv"):
    owner_id: int
    page: str
    number: int = 1


def _inventory_button(label: str, owner_id: int, page: str, number: int = 1) -> InlineKeyboardButton:
    return InlineKeyboardButton(
        text=label,
        callback_data=InventoryPage(owner_id=owner_id, page=page, number=number).pack(),
    )


def _inventory_switch_row(owner_id: int, current: str) -> list[InlineKeyboardButton]:
    return [
        _inventory_button(text(label_key), owner_id, page)
        for page, label_key in (
            (INVENTORY_MAIN, "inventory.balls_button"),
            (INVENTORY_KEY_ITEMS, "inventory.key_items_button"),
            (INVENTORY_TMS, "inventory.tms_button"),
        )
        if page != current
    ]


def inventory_main_keyboard(owner_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[_inventory_switch_row(owner_id, INVENTORY_MAIN)])


def inventory_key_items_keyboard(owner_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[_inventory_switch_row(owner_id, INVENTORY_KEY_ITEMS)])


def inventory_tms_keyboard(owner_id: int, page: int, pages: int) -> InlineKeyboardMarkup:
    rows = pokemon_list.page_rows(
        page,
        pages,
        [],
        _inventory_button(text("pokemon_list.page_indicator", page=page, pages=pages), owner_id, INVENTORY_TMS, page),
        lambda label_key, delta: _inventory_button(
            text(f"pokemon_list.{label_key}"), owner_id, INVENTORY_TMS, page + delta
        ),
    )
    rows.append(_inventory_switch_row(owner_id, INVENTORY_TMS))
    return InlineKeyboardMarkup(inline_keyboard=rows)


class ReleaseAction(CallbackData, prefix="rel"):
    owner_id: int
    pokemon_id: str
    action: str


def caught_keyboard(owner_id: int, pokemon_id: str, dex_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text=text("hunt.view_stats_button"),
        callback_data=StatsOpen(owner_id=owner_id, pokemon_id=pokemon_id),
    )
    builder.button(
        text=text("hunt.view_pokedex_button"),
        callback_data=PokedexEntry(dex_id=dex_id),
    )
    builder.button(
        text=text("hunt.nickname_button"),
        callback_data=NicknameChoice(owner_id=owner_id, pokemon_id=pokemon_id),
    )
    builder.button(
        text=text("hunt.release_button"),
        callback_data=ReleaseAction(owner_id=owner_id, pokemon_id=pokemon_id, action="ask"),
    )
    builder.adjust(2)
    return builder.as_markup()


def release_keyboard(owner_id: int, pokemon_id: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for label_key, action in (("release.yes_button", "yes"), ("release.no_button", "no")):
        builder.button(
            text=text(label_key),
            callback_data=ReleaseAction(owner_id=owner_id, pokemon_id=pokemon_id, action=action),
        )
    builder.adjust(2)
    return builder.as_markup()
