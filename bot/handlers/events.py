from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.game import events
from bot.handlers.journey import JourneyRequired
from bot.ui.texts import text

router = Router()
router.message.middleware(JourneyRequired())


@router.message(Command("events"), F.from_user)
async def events_command(message: Message) -> None:
    today = datetime.now(timezone.utc).date()
    await message.reply(
        text(
            "events.daily",
            date=today.strftime("%b %d, %Y"),
            name=events.event_name(events.daily_event(message.from_user.id, today)),
        )
    )
