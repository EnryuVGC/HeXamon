from dataclasses import dataclass
from datetime import datetime

from bot.game import trainer_stats as rules
from bot.storage.stores import Stores


@dataclass
class TrainerStats:
    trainer_id: int
    rank: int
    exp_points: int
    to_next_rank: int
    wins: int
    losses: int
    started_at: datetime
    win_ratio: float
    balls_used: int
    total_caught: int
    catch_rate: float
    seen: int
    obtained: int


async def stats_of(stores: Stores, trainer_id: int) -> TrainerStats | None:
    trainer = await stores.trainers.get(trainer_id)
    if trainer is None:
        return None
    exp_points = trainer.get("exp_points", 0)
    wins, losses = trainer.get("wins", 0), trainer.get("losses", 0)
    balls_used, total_caught = trainer.get("balls_used", 0), trainer.get("total_caught", 0)
    caught_dex = set(trainer["caught_dex"])
    return TrainerStats(
        trainer_id=trainer_id,
        rank=rules.rank_of(exp_points),
        exp_points=exp_points,
        to_next_rank=rules.to_next_rank(exp_points),
        wins=wins,
        losses=losses,
        started_at=trainer["created_at"],
        win_ratio=rules.win_ratio(wins, losses),
        balls_used=balls_used,
        total_caught=total_caught,
        catch_rate=rules.catch_rate(total_caught, balls_used),
        seen=rules.species_count(caught_dex | set(trainer["seen_dex"])),
        obtained=rules.species_count(caught_dex),
    )
