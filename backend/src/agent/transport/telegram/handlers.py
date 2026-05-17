from __future__ import annotations

import logging
from typing import Callable

from aiogram import Dispatcher
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlmodel import Session, select

from agent.transport.proposal import parse_proposal
from agent.transport.telegram.keyboard import confirm_decline_keyboard
from stow.db import engine
from stow.models import TelegramUser

logger = logging.getLogger(__name__)

_HELP_TEXT = """\
Stow — personal finance assistant

Commands:
  /balance — account balances
  /recurring — today's recurring transactions
  /import — import a bank statement PDF
  /help — show this message

Or just type naturally:
  "paid ₹850 for Zomato from HDFC"
  "how much did I spend on food this month?"
"""

_SLASH_PROMPTS: dict[str, str] = {
    "balance": "/balance",
    "recurring": "/recurring",
    "import": "/import",
}

# Per-user conversation history: {telegram_user_id: list[ModelMessage]}
_history: dict[int, list] = {}


def _get_orchestrator_runner() -> Callable:
    from agent.orchestrator import build_orchestrator
    from agent.deps import StowDeps
    import httpx

    _orch = build_orchestrator()

    async def run(prompt: str, user_id: int) -> str:
        history = _history.get(user_id, [])
        async with httpx.AsyncClient(timeout=60.0) as client:
            deps = StowDeps.build()
            deps.http_client = client
            result = await _orch.run(prompt, deps=deps, message_history=history)
            _history[user_id] = result.all_messages()
            return result.output

    return run


def register_handlers(dp: Dispatcher) -> None:
    _run = _get_orchestrator_runner()

    @dp.message(Command("start"))
    async def cmd_start(message: Message) -> None:
        if message.from_user is None:
            return
        tg_id = message.from_user.id
        username = message.from_user.username

        with Session(engine) as session:
            existing = session.exec(
                select(TelegramUser).where(TelegramUser.telegram_user_id == tg_id)
            ).first()
            if existing:
                existing.username = username
            else:
                session.add(TelegramUser(telegram_user_id=tg_id, username=username))
            session.commit()

        _history.pop(tg_id, None)  # fresh session on /start
        await message.answer(
            "Welcome to Stow! 👋\n\n"
            "Type a transaction, ask a question, or send a bank statement PDF.\n"
            "Use /help to see all commands."
        )

    @dp.message(Command("help"))
    async def cmd_help(message: Message) -> None:
        await message.answer(_HELP_TEXT)

    @dp.message(Command("balance"))
    async def cmd_balance(message: Message) -> None:
        if message.from_user is None:
            return
        reply = await _run("/balance", message.from_user.id)
        await _send_reply(message, reply, message.from_user.id)

    @dp.message(Command("recurring"))
    async def cmd_recurring(message: Message) -> None:
        if message.from_user is None:
            return
        reply = await _run("/recurring", message.from_user.id)
        await _send_reply(message, reply, message.from_user.id)

    @dp.message(Command("import"))
    async def cmd_import(message: Message) -> None:
        await message.answer("Please send a bank statement PDF file.")

    @dp.message()
    async def handle_message(message: Message) -> None:
        if message.from_user is None:
            return
        user_id = message.from_user.id

        if message.photo:
            photo = message.photo[-1]
            file = await message.bot.get_file(photo.file_id)  # type: ignore[union-attr]
            file_bytes = await message.bot.download_file(file.file_path)  # type: ignore[union-attr]
            import base64
            b64 = base64.b64encode(file_bytes.read()).decode()
            prompt = f"[IMAGE:{b64}] {message.caption or 'Process this payment screenshot'}"
            reply = await _run(prompt, user_id)
            await _send_reply(message, reply, user_id)

        elif message.document and message.document.file_name and message.document.file_name.lower().endswith(".pdf"):
            file = await message.bot.get_file(message.document.file_id)  # type: ignore[union-attr]
            file_bytes = await message.bot.download_file(file.file_path)  # type: ignore[union-attr]
            import base64
            b64 = base64.b64encode(file_bytes.read()).decode()
            fname = message.document.file_name
            prompt = f"[PDF:{b64}:{fname}] Import this bank statement"
            reply = await _run(prompt, user_id)
            await _send_reply(message, reply, user_id)

        elif message.text:
            reply = await _run(message.text, user_id)
            await _send_reply(message, reply, user_id)

    @dp.callback_query()
    async def handle_callback(callback: CallbackQuery) -> None:
        if callback.data and callback.from_user:
            user_id = callback.from_user.id
            reply = await _run(callback.data, user_id)
            await _send_reply(callback.message, reply, user_id)  # type: ignore[arg-type]
        await callback.answer()


async def _send_reply(message: Message, text: str, user_id: int) -> None:
    """Send reply, attaching an inline keyboard when the response is a proposal."""
    proposal, display = parse_proposal(text)
    if proposal:
        keyboard = confirm_decline_keyboard(confirm_data="confirm", decline_data="decline")
        await message.answer(display or text, reply_markup=keyboard)
    else:
        await message.answer(text)
