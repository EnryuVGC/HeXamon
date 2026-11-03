from dataclasses import dataclass

from motor.motor_asyncio import AsyncIOMotorDatabase

from bot.storage.bans import BanStore
from bot.storage.challenges import ChallengeStore
from bot.storage.lottery import LotteryStore
from bot.storage.pokemon import PokemonStore
from bot.storage.trades import TradeStore
from bot.storage.trainers import TrainerStore


@dataclass(frozen=True)
class Stores:
    trainers: TrainerStore
    pokemon: PokemonStore
    trades: TradeStore
    challenges: ChallengeStore
    lottery: LotteryStore
    bans: BanStore

    @classmethod
    def of(cls, database: AsyncIOMotorDatabase) -> "Stores":
        return cls(
            trainers=TrainerStore(database),
            pokemon=PokemonStore(database),
            trades=TradeStore(database),
            challenges=ChallengeStore(database),
            lottery=LotteryStore(database),
            bans=BanStore(database),
        )

    async def ensure_indexes(self) -> None:
        await self.pokemon.ensure_indexes()
        await self.trainers.ensure_indexes()
        await self.trades.ensure_indexes()
        await self.challenges.ensure_indexes()
