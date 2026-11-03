import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    bot_token: str
    mongo_uri: str
    mongo_database: str
    admin_ids: frozenset[int]
    bot_api_url: str | None


def _admin_ids(raw: str) -> frozenset[int]:
    return frozenset(int(value) for value in raw.split(",") if value.strip().isdecimal())


def load_settings() -> Settings:
    load_dotenv()
    return Settings(
        bot_token=os.environ["BOT_TOKEN"],
        mongo_uri=os.environ["MONGO_URI"],
        mongo_database=os.environ["MONGO_DATABASE"],
        admin_ids=_admin_ids(os.environ.get("ADMIN_IDS", "")),
        bot_api_url=os.environ.get("BOT_API_URL", "").strip() or None,
    )
