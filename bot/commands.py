"""Bot menu commands setup — called once on startup."""
from __future__ import annotations

from aiogram import Bot
from aiogram.types import (
    BotCommand,
    BotCommandScopeDefault,
    BotCommandScopeChat,
    MenuButtonCommands,
)

from config import load_config

_config = load_config()

USER_COMMANDS = [
    BotCommand(command="start",     description="🏠 Главное меню"),
    BotCommand(command="help",      description="📋 Инструкция"),
]

ADMIN_COMMANDS = [
    BotCommand(command="start",     description="🏠 Главное меню"),
    BotCommand(command="admin",     description="⚙️ Панель администратора"),
    BotCommand(command="help",      description="📋 Инструкция"),
]


async def setup_commands(bot: Bot) -> None:
    await bot.set_my_commands(USER_COMMANDS, scope=BotCommandScopeDefault())
    for admin_id in _config.admin_ids:
        try:
            await bot.set_my_commands(
                ADMIN_COMMANDS,
                scope=BotCommandScopeChat(chat_id=admin_id),
            )
        except Exception:
            pass
    await bot.set_chat_menu_button(menu_button=MenuButtonCommands())
