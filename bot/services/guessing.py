from dataclasses import dataclass
from time import monotonic

from bot.game import guessing as rules
from bot.storage.stores import Stores


@dataclass
class GuessRound:
    answer: str
    image: str
    started_at: float | None = None


_rounds: dict[int, GuessRound] = {}


def reserve(chat_id: int) -> GuessRound | None:
    if chat_id in _rounds:
        return None
    dex_id = rules.pick()
    game_round = GuessRound(rules.answer_of(dex_id), rules.image_of(dex_id))
    _rounds[chat_id] = game_round
    return game_round


def start(game_round: GuessRound) -> None:
    game_round.started_at = monotonic()


def cancel(chat_id: int, game_round: GuessRound) -> None:
    if _rounds.get(chat_id) is game_round:
        del _rounds[chat_id]


def is_running(chat_id: int, game_round: GuessRound) -> bool:
    return _rounds.get(chat_id) is game_round


def open_round(chat_id: int) -> GuessRound | None:
    game_round = _rounds.get(chat_id)
    return game_round if game_round and game_round.started_at is not None else None


async def claim_win(stores: Stores, chat_id: int, game_round: GuessRound, trainer_id: int) -> tuple[float, int] | None:
    if _rounds.get(chat_id) is not game_round:
        return None
    del _rounds[chat_id]
    paid = await stores.trainers.earn_money(trainer_id, rules.REWARD)
    return monotonic() - game_round.started_at, paid or 0
