import time
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.enums import ChatType
from aiogram.types import CallbackQuery

from bot.ui.texts import text

BUTTON_COOLDOWN_SECONDS = 2
COOLDOWNS_KEPT = 1000


class ButtonCooldown(BaseMiddleware):
    def __init__(self, groups_only: bool = False) -> None:
        self._ready_at: dict[int, float] = {}
        self._groups_only = groups_only

    async def __call__(
        self,
        handler: Callable[[CallbackQuery, dict[str, Any]], Awaitable[Any]],
        event: CallbackQuery,
        data: dict[str, Any],
    ) -> Any:
        if self._groups_only and (event.message is None or event.message.chat.type == ChatType.PRIVATE):
            return await handler(event, data)
        now = time.monotonic()
        if now < self._ready_at.get(event.from_user.id, 0):
            await event.answer(text("common.cooldown"))
            return None
        if len(self._ready_at) >= COOLDOWNS_KEPT:
            self._ready_at = {user: ready for user, ready in self._ready_at.items() if ready > now}
        self._ready_at[event.from_user.id] = now + BUTTON_COOLDOWN_SECONDS
        return await handler(event, data)


group_item_cooldown = ButtonCooldown(groups_only=True)
