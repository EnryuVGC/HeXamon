import time
from html import escape
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware, F, Router
from aiogram.filters import BaseFilter, Command, CommandObject
from aiogram.types import CallbackQuery, Message, TelegramObject, User

from bot.data import catalog
from bot.game import admin as rules
from bot.game import pokedex
from bot.services import admin
from bot.storage.stores import Stores
from bot.ui.texts import text

router = Router()
public_router = Router()


class BannedUsers(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = event.from_user
        if user is None or user.id in data["admin_ids"] or not await data["stores"].bans.is_banned(user.id):
            return await handler(event, data)
        if isinstance(event, CallbackQuery):
            await event.answer()


class IsAdmin(BaseFilter):
    async def __call__(self, message: Message, admin_ids: frozenset[int]) -> bool:
        return message.from_user is not None and message.from_user.id in admin_ids


router.message.filter(IsAdmin())

REFUSALS = {
    admin.NOT_STARTED: "admin.not_started",
    admin.IN_TRADE: "trade.locked",
    admin.NOT_ENOUGH: "admin.not_enough",
    admin.FAILED: "admin.failed",
}


def _target(message: Message) -> User:
    replied = message.reply_to_message
    if replied is None or replied.forum_topic_created or replied.from_user is None or replied.from_user.is_bot:
        return message.from_user
    return replied.from_user


def _name(user: User) -> str:
    return escape(user.first_name)


def _thing(grant: rules.Grant) -> str:
    if grant.kind == rules.MONEY:
        return text("admin.thing_money", amount=grant.amount)
    if grant.kind == rules.BALL:
        label = text(f"inventory.balls.{grant.key}.{'one' if grant.amount == 1 else 'many'}")
        return text("admin.thing_count", amount=grant.amount, label=label)
    if grant.kind == rules.ITEM:
        label = text(f"inventory.items.{grant.key}.{'one' if grant.amount == 1 else 'many'}")
        return text("admin.thing_count", amount=grant.amount, label=label)
    if grant.kind == rules.TM:
        move = pokedex.display_name(catalog.load("technical_machines")[grant.key]["name"])
        return text("admin.thing_tm", amount=grant.amount, number=int(grant.key), move=move)
    if grant.kind == rules.POKEMON:
        return text("admin.thing_pokemon", level=grant.amount, name=pokedex.species_name(int(grant.key)))
    if grant.kind == rules.KEY_STONE:
        return text("admin.thing_key_stone")
    if grant.kind == rules.EGG:
        return text("admin.thing_eggs", amount=grant.amount)
    if grant.kind == rules.EXP:
        return text("admin.thing_exp", amount=grant.amount)
    return grant.key


async def _reply_refusal(message: Message, status: str, user: User) -> None:
    await message.reply(text(REFUSALS[status], user=_name(user)))


@public_router.message(Command("myid"), F.from_user)
async def myid_command(message: Message) -> None:
    await message.reply(text("admin.your_id", id=_target(message).id))


@router.message(Command("admin"))
async def admin_command(message: Message) -> None:
    await message.reply(text("admin.help"))


@router.message(Command("add"))
async def add_command(message: Message, command: CommandObject, stores: Stores) -> None:
    grant = rules.parse_grant(command.args)
    if grant is None:
        await message.reply(text("admin.add_format"))
        return
    user = _target(message)
    result = await admin.add(stores, user.id, grant)
    if result.status != admin.DONE:
        await _reply_refusal(message, result.status, user)
        return
    await message.reply(text("admin.added", thing=_thing(grant), user=_name(user)))


@router.message(Command("remove"))
async def remove_command(message: Message, command: CommandObject, stores: Stores) -> None:
    grant = rules.parse_grant(command.args)
    if grant is None or grant.kind in (rules.POKEMON, rules.EGG):
        await message.reply(text("admin.remove_format"))
        return
    user = _target(message)
    result = await admin.remove(stores, user.id, grant)
    if result.status != admin.DONE:
        await _reply_refusal(message, result.status, user)
        return
    await message.reply(text("admin.removed", thing=_thing(grant), user=_name(user)))


def _target_id(message: Message, command: CommandObject) -> int | None:
    trainer_id = rules.parse_target_id(command.args)
    if trainer_id is not None:
        return trainer_id
    target = _target(message)
    return target.id if target.id != message.from_user.id else None


@router.message(Command("ban"))
async def ban_command(message: Message, command: CommandObject, stores: Stores, admin_ids: frozenset[int]) -> None:
    trainer_id = _target_id(message, command)
    if trainer_id is None:
        await message.reply(text("admin.ban_format"))
    elif trainer_id in admin_ids:
        await message.reply(text("admin.cannot_ban_admin"))
    elif await stores.bans.ban(trainer_id):
        await message.reply(text("admin.banned", id=trainer_id))
    else:
        await message.reply(text("admin.already_banned", id=trainer_id))


@router.message(Command("unban"))
async def unban_command(message: Message, command: CommandObject, stores: Stores) -> None:
    trainer_id = _target_id(message, command)
    if trainer_id is None:
        await message.reply(text("admin.unban_format"))
    elif await stores.bans.unban(trainer_id):
        await message.reply(text("admin.unbanned", id=trainer_id))
    else:
        await message.reply(text("admin.not_banned", id=trainer_id))


@router.message(Command("ping"))
async def ping_command(message: Message) -> None:
    started = time.monotonic()
    sent = await message.reply(text("admin.pinging"))
    await sent.edit_text(text("admin.pong", ms=round((time.monotonic() - started) * 1000)))
