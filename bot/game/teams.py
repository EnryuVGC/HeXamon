import random

TEAM_COUNT = 6
TEAM_SIZE = 6


def team_numbers() -> range:
    return range(1, TEAM_COUNT + 1)


def empty_teams() -> dict:
    return {str(number): [] for number in team_numbers()}


def shuffled(members: list[str]) -> list[str]:
    result = list(members)
    while result == members and len(set(members)) > 1:
        random.shuffle(result)
    return result


def swapped(members: list[str], first: int, second: int) -> list[str]:
    result = list(members)
    result[first], result[second] = result[second], result[first]
    return result
