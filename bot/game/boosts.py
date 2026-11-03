from bot.game.creatures import MAX_IV

BOOST = "boost"
IV_POINTS = 1


def can_boost(pokemon: dict, stat: int) -> bool:
    return pokemon["ivs"][stat] < MAX_IV and str(stat) not in pokemon.get("boosts", {})


def boostable_stats(pokemon: dict) -> list[int]:
    return [stat for stat in range(len(pokemon["ivs"])) if can_boost(pokemon, stat)]


def after_boost(ivs: list[int], stat: int) -> list[int]:
    return [value + IV_POINTS if index == stat else value for index, value in enumerate(ivs)]
