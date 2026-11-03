import random
from unicodedata import normalize

from bot.game import pokedex
from bot.game.trainer_stats import NATIONAL_DEX_SIZE

REWARD = 5
HINT_AFTER_SECONDS = 30
HINT_SECONDS = 10
IMAGE_URL = "https://t.me/guessimages/{post}"
EXTRA_REVEALS = {4: 1, 5: 2, 6: 2, 7: 3, 8: 3}
SHORT_NAME_LENGTH = 9
LONG_NAME_REVEALS = 4
ALWAYS_SHOWN = (" ", ".")
HIDDEN_LETTER = "_"


def pick() -> int:
    return random.randint(1, NATIONAL_DEX_SIZE)


def answer_of(dex_id: int) -> str:
    return pokedex.plain_name(dex_id)


def image_of(dex_id: int) -> str:
    return IMAGE_URL.format(post=dex_id + 1)


def _spelling(name: str) -> str:
    return "".join(character for character in normalize("NFKD", name).casefold() if character.isalnum())


def is_correct(guess: str, answer: str) -> bool:
    return _spelling(guess) == _spelling(answer)


def _extra_reveals(length: int) -> int:
    if length <= SHORT_NAME_LENGTH:
        return EXTRA_REVEALS.get(length, 0)
    return LONG_NAME_REVEALS + (length - SHORT_NAME_LENGTH) // 2


def make_hint(name: str) -> str:
    letters = [index for index, character in enumerate(name) if character not in ALWAYS_SHOWN]
    shown = {letters[0], letters[-1]}
    hidden = [index for index in letters if index not in shown]
    shown.update(random.sample(hidden, min(_extra_reveals(len(name)), len(hidden))))
    return "".join(
        character if index in shown or character in ALWAYS_SHOWN else HIDDEN_LETTER
        for index, character in enumerate(name)
    )
