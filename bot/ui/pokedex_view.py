from html import escape

from bot.game import experience, pokedex
from bot.game import pokedex_entries as rules
from bot.ui.texts import text


def _types(dex_id: int) -> str:
    return text("battle.type_separator").join(
        text(
            "stats.type",
            name=pokedex.display_name(type_name),
            symbol=text(f"display.type_symbols.{type_name}"),
        )
        for type_name in pokedex.entry(dex_id)["types"]
    )


def _list_line(number: int, dex_id: int, seen: set[int], caught: set[int]) -> str:
    name = pokedex.species_name(dex_id) if dex_id in seen else text("pokedex.unseen_name")
    marker = text("hunt.caught_marker") if dex_id in caught else ""
    return text("pokedex.list_line", number=number, name=name, marker=marker)


def list_text(page) -> str:
    return "\n".join(
        _list_line(number, dex_id, page.seen, page.caught)
        for number, dex_id in enumerate(page.dex_ids, start=page.first_number)
    )


def _form_title(dex_id: int) -> str | None:
    words = rules.form_words(dex_id)
    if not words:
        return None
    if rules.MEGA in words:
        extra = " ".join(word.title() for word in words if word != rules.MEGA)
        return text("pokedex.mega_title", extra=extra).strip()
    return text("pokedex.form_title", form=" ".join(word.title() for word in words))


def _about_text(dex_id: int) -> str:
    regions = rules.regions_found(dex_id)
    about = text(
        "pokedex.about",
        number=rules.species_of(dex_id),
        name=pokedex.base_species_name(dex_id),
        types=_types(dex_id),
        catch=text(f"pokedex.catch_levels.{rules.catch_level(dex_id)}"),
        growth=pokedex.display_name(rules.growth_rate(dex_id)),
        regions=", ".join(regions) if regions else text("pokedex.no_regions"),
    )
    title = _form_title(dex_id)
    return f"{text('pokedex.title_line', title=title)}\n{about}" if title else about


def _stats_text(dex_id: int) -> str:
    stats = pokedex.entry(dex_id)["stats"]
    return "\n".join(
        text("pokedex.page_line", label=text(f"hunt.ev_stats.{stat}"), value=stats[stat])
        for stat in experience.STAT_NAMES
    )


def _evs_text(dex_id: int) -> str:
    yields = pokedex.entry(dex_id)["ev_yield"]
    lines = [
        text("pokedex.page_line", label=text(f"hunt.ev_stats.{stat}"), value=f"+{yields[stat]}")
        for stat in experience.STAT_NAMES
        if yields.get(stat)
    ]
    return "\n".join(lines) or text("pokedex.no_evs")


def suggestion_text(dex_id: int) -> str:
    return text("pokemon_picker.did_you_mean", name=escape(pokedex.species_name(dex_id)))


def page_text(dex_id: int, view: str) -> str:
    pages = {rules.ABOUT: _about_text, rules.BASE_STATS: _stats_text, rules.EV_YIELDS: _evs_text}
    return pages[view](dex_id)
