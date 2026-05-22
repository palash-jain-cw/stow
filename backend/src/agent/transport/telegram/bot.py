from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from aiogram import Bot, Dispatcher
from aiogram.utils.token import TokenValidationError

logger = logging.getLogger(__name__)

_bot: Bot | None = None
_dispatcher: Dispatcher | None = None
_polling_task: asyncio.Task | None = None


def get_bot() -> Bot | None:
    """Return the running Bot instance, or None if Telegram is disabled."""
    return _bot


def is_bot_running() -> bool:
    return _polling_task is not None and not _polling_task.done()


def _read_token() -> str | None:
    from stow.telegram_config import read_telegram_config

    token = read_telegram_config().get("bot_token", "").strip()
    return token or None


def _on_polling_done(task: asyncio.Task) -> None:
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        logger.exception("Telegram polling stopped unexpectedly: %s", exc)


async def stop_bot() -> None:
    global _bot, _dispatcher, _polling_task

    if _polling_task is not None:
        try:
            _polling_task.remove_done_callback(_on_polling_done)
        except ValueError:
            pass
        _polling_task.cancel()
        try:
            await _polling_task
        except asyncio.CancelledError:
            pass
        _polling_task = None

    if _bot is not None:
        await _bot.session.close()
        _bot = None
    _dispatcher = None
    logger.info("Telegram bot stopped")


async def start_bot() -> bool:
    """Start long-polling if a token is configured. Returns True when running."""
    global _bot, _dispatcher, _polling_task

    token = _read_token()
    if not token:
        logger.warning("Telegram bot token not configured — bot disabled")
        return False

    try:
        _bot = Bot(token=token)
    except TokenValidationError:
        logger.exception("Telegram bot token is invalid — bot disabled")
        _bot = None
        return False

    _dispatcher = Dispatcher()

    from agent.transport.telegram.handlers import register_handlers

    register_handlers(_dispatcher)
    _polling_task = asyncio.create_task(
        _dispatcher.start_polling(_bot, handle_signals=False),
        name="telegram-polling",
    )
    _polling_task.add_done_callback(_on_polling_done)
    logger.info("Telegram bot started")
    return True


async def reload_bot() -> bool:
    """Restart the bot after config changes."""
    await stop_bot()
    return await start_bot()


def create_bot_and_dispatcher() -> tuple[Bot | None, Dispatcher | None]:
    """Build bot + dispatcher without starting polling (for tests)."""
    token = _read_token()
    if not token:
        return None, None
    try:
        bot = Bot(token=token)
    except TokenValidationError:
        logger.exception("Telegram bot token is invalid")
        return None, None
    dp = Dispatcher()
    from agent.transport.telegram.handlers import register_handlers

    register_handlers(dp)
    return bot, dp


@asynccontextmanager
async def lifespan_telegram(app: object) -> AsyncGenerator[None, None]:
    try:
        started = await start_bot()
        if not started and _read_token():
            logger.error(
                "Telegram token is configured but the bot failed to start — "
                "re-save the token in Settings → Telegram"
            )
        yield
    finally:
        await stop_bot()
