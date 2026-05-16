from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from aiogram import Bot, Dispatcher

logger = logging.getLogger(__name__)


def create_bot_and_dispatcher() -> tuple[Bot, Dispatcher] | tuple[None, None]:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.warning("TELEGRAM_BOT_TOKEN not set — Telegram bot disabled")
        return None, None
    bot = Bot(token=token)
    dp = Dispatcher()
    return bot, dp


async def start_polling(bot: Bot, dp: Dispatcher) -> None:
    await dp.start_polling(bot, handle_signals=False)


@asynccontextmanager
async def lifespan_telegram(app: object) -> AsyncGenerator[None, None]:
    bot, dp = create_bot_and_dispatcher()
    if bot is None:
        yield
        return

    from agent.transport.telegram.handlers import register_handlers
    register_handlers(dp)

    task = asyncio.create_task(start_polling(bot, dp))
    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        await bot.session.close()
