from html import escape

from bot.game import pokedex
from bot.game import trades as rules
from bot.game.stats_pages import IVS
from bot.ui import pokemon_list, stats_view
from bot.ui.texts import text


def _mention(side: dict) -> str:
    return text("trade.mention", trainer_id=side["id"], name=escape(side["name"]))


def _true_name(dex_id: int, nickname: str | None) -> str:
    species = pokedex.species_name(dex_id)
    return text("trade.nicknamed", nickname=escape(nickname), species=species) if nickname else species


def request_text(trade: dict) -> str:
    return text(
        "trade.request",
        requester=_mention(trade[rules.REQUESTER]),
        partner=_mention(trade[rules.PARTNER]),
    )


def choose_text(trade: dict, collection) -> str:
    return text(
        "trade.choose",
        trainer=_mention(trade[rules.CHOOSER_SIDE[trade["state"]]]),
        pokemon=pokemon_list.lines(collection.page.pokemon, collection.display, force_numbers=True),
    )


def _offer_text(side: dict, pokemon: dict) -> str:
    return text(
        "trade.offer",
        trainer=_mention(side),
        name=_true_name(pokemon["dex_id"], pokemon["nickname"]) + pokemon_list.badges(pokemon),
        level=pokemon["level"],
        nature=pokemon["nature"],
        points=stats_view.page_text(IVS, pokemon),
    )


def confirm_text(trade: dict, offered: list[dict]) -> str:
    requester, partner = offered
    return text(
        "trade.confirm",
        requester=_offer_text(trade[rules.REQUESTER], requester),
        partner=_offer_text(trade[rules.PARTNER], partner),
    )


def result_text(trade: dict) -> str:
    if trade["state"] != rules.DONE:
        return text(f"trade.{trade['outcome']}")
    requester, partner = trade[rules.REQUESTER], trade[rules.PARTNER]
    return text(
        "trade.confirmed",
        requester=_mention(requester),
        requester_pokemon=pokedex.species_name(partner["offer"]["dex_id"]),
        partner=_mention(partner),
        partner_pokemon=pokedex.species_name(requester["offer"]["dex_id"]),
    )
