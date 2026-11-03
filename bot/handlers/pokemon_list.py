from aiogram import Router
from aiogram.types import CallbackQuery

from bot.ui.pokemon_list import PokemonListIndicator

router = Router()


@router.callback_query(PokemonListIndicator.filter())
async def page_indicator_pressed(callback: CallbackQuery) -> None:
    await callback.answer()
