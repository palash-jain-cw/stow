from __future__ import annotations

import logging
import re
import traceback
from typing import Callable

from aiogram import Dispatcher
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlmodel import Session, select

from agent.transport.proposal import parse_proposal
from agent.transport.telegram.keyboard import confirm_decline_keyboard
from agent.history import trim_message_history
from stow.ai_config import model_settings
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


def clear_conversation_history() -> None:
    """Drop cached Telegram message history after LLM config changes."""
    _history.clear()
    logger.info("Telegram conversation history cleared after LLM config change")


def _get_orchestrator_runner() -> Callable:
    from agent.orchestrator import build_orchestrator
    from agent.deps import StowDeps
    import asyncio
    import httpx

    async def _keep_typing(bot, chat_id: int, stop: asyncio.Event) -> None:
        while not stop.is_set():
            try:
                await bot.send_chat_action(chat_id, "typing")
            except Exception:
                pass
            await asyncio.sleep(4)

    async def run(prompt: str | list, user_id: int, message: object | None = None) -> str:
        if not isinstance(prompt, str):
            return await _run_orchestrator(prompt, user_id, message)

        user_key = str(user_id)
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                base_url = StowDeps.build().base_url

                if prompt.startswith("cfm:"):
                    from agent.transport.proposal import confirm_pending_proposal

                    action = await confirm_pending_proposal(
                        user_key, prompt[4:], client, base_url
                    )
                    if action.kind == "agent":
                        return await _run_orchestrator(action.message, user_id, message)
                    return action.message

                if prompt.startswith("dec:"):
                    from agent.transport.proposal import decline_pending_proposal

                    return decline_pending_proposal(user_key, prompt[4:])

                from agent.transport.proposal import handle_proposal_action

                action = await handle_proposal_action(
                    prompt, client, base_url, user_key=user_key
                )
                if action.kind == "reply":
                    return action.message
                if action.kind == "agent":
                    return await _run_orchestrator(action.message, user_id, message)

            return await _run_orchestrator(prompt, user_id, message)
        except Exception:
            logger.exception("Telegram message handling failed")
            return "Sorry, I couldn't process that request. Check Settings → AI / LLM and try again."

    async def _run_orchestrator(prompt: str | list, user_id: int, message: object | None = None) -> str:
        try:
            orchestrator = build_orchestrator()
            history = trim_message_history(_history.get(user_id, []))
            async with httpx.AsyncClient(timeout=120.0) as client:
                deps = StowDeps.build()
                deps.http_client = client

                stop_typing = asyncio.Event()
                typing_task = None
                if message is not None:
                    try:
                        typing_task = asyncio.create_task(
                            _keep_typing(message.bot, message.chat.id, stop_typing)  # type: ignore[union-attr]
                        )
                    except Exception:
                        pass

                try:
                    result = await orchestrator.run(
                        prompt,
                        deps=deps,
                        message_history=history,
                        model_settings=model_settings("orchestrator"),
                    )
                finally:
                    stop_typing.set()
                    if typing_task is not None:
                        typing_task.cancel()

                _history[user_id] = trim_message_history(result.all_messages())
                return result.output
        except Exception:
            logger.exception("Telegram orchestrator run failed")
            return "Sorry, I couldn't process that request. Check Settings → AI / LLM and try again."

    return run


def register_handlers(dp: Dispatcher) -> None:
    _run = _get_orchestrator_runner()

    @dp.errors()
    async def on_error(event) -> bool:
        logger.error(
            "Telegram handler error for update %s",
            event.update.update_id if event.update else "?",
            exc_info=event.exception,
        )
        update = event.update
        if update.message:
            try:
                await update.message.answer(
                    "Sorry, something went wrong while handling your message. "
                    "Try again or use /help."
                )
            except Exception:
                logger.exception("Failed to send Telegram error reply")
        return True

    @dp.message(Command("start"))
    async def cmd_start(message: Message) -> None:
        if message.from_user is None:
            return
        tg_id = message.from_user.id
        username = message.from_user.username

        try:
            with Session(engine) as session:
                existing = session.exec(
                    select(TelegramUser).where(TelegramUser.telegram_user_id == tg_id)
                ).first()
                if existing:
                    existing.username = username
                else:
                    session.add(TelegramUser(telegram_user_id=tg_id, username=username))
                session.commit()
        except Exception:
            logger.exception("Failed to register Telegram user %s", tg_id)

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
        reply = await _run("/balance", message.from_user.id, message)
        await _send_reply(message, reply, message.from_user.id)

    @dp.message(Command("recurring"))
    async def cmd_recurring(message: Message) -> None:
        if message.from_user is None:
            return
        reply = await _run("/recurring", message.from_user.id, message)
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
            from pydantic_ai.messages import BinaryContent
            photo = message.photo[-1]
            file = await message.bot.get_file(photo.file_id)  # type: ignore[union-attr]
            file_bytes = await message.bot.download_file(file.file_path)  # type: ignore[union-attr]
            prompt = [
                message.caption or "Process this payment screenshot",
                BinaryContent(data=file_bytes.read(), media_type="image/jpeg"),
            ]
            reply = await _run(prompt, user_id, message)
            await _send_reply(message, reply, user_id)

        elif message.document and message.document.file_name and message.document.file_name.lower().endswith(".pdf"):
            import httpx as _httpx
            import os as _os
            from agent.transport.websocket import _upload_pdf_to_batch
            file = await message.bot.get_file(message.document.file_id)  # type: ignore[union-attr]
            file_bytes = await message.bot.download_file(file.file_path)  # type: ignore[union-attr]
            fname = message.document.file_name
            base_url = _os.environ.get("STOW_BASE_URL", "http://localhost:8000")
            async with _httpx.AsyncClient(timeout=120.0) as _client:
                prompt = await _upload_pdf_to_batch(file_bytes.read(), fname, _client, base_url)
            reply = await _run(prompt, user_id, message)
            await _send_reply(message, reply, user_id)

        elif message.text:
            reply = await _run(message.text, user_id, message)
            await _send_reply(message, reply, user_id)

    @dp.callback_query()
    async def handle_callback(callback: CallbackQuery) -> None:
        if callback.data and callback.from_user:
            user_id = callback.from_user.id
            reply = await _run(callback.data, user_id, callback.message)
            await _send_reply(callback.message, reply, user_id)  # type: ignore[arg-type]
        await callback.answer()


def _md_to_html(text: str) -> str:
    """Convert LLM markdown output to Telegram-compatible HTML."""
    import html
    import markdown as _md

    # Strip PROPOSAL: lines (handled separately as keyboard)
    lines = [l for l in text.splitlines() if not l.startswith("PROPOSAL:")]
    text = "\n".join(lines)

    # Convert to HTML, then strip tags Telegram doesn't support
    raw = _md.markdown(text, extensions=["fenced_code", "tables"])

    # Telegram HTML supports: b, strong, i, em, u, s, code, pre, a, blockquote
    # Strip unsupported tags (h1-h6 → b, others removed)
    raw = re.sub(r"<h[1-6][^>]*>(.*?)</h[1-6]>", r"<b>\1</b>", raw, flags=re.S)
    raw = re.sub(r"<(ul|ol|li|p|div|span|table|thead|tbody|tr|th|td)[^>]*>", "", raw)
    raw = re.sub(r"</(ul|ol|li|p|div|span|table|thead|tbody|tr|th|td)>", "\n", raw)
    raw = re.sub(r"\n{3,}", "\n\n", raw).strip()
    return raw


async def _send_reply(message: Message, text: str, user_id: int) -> None:
    """Send reply, attaching an inline keyboard when the response is a proposal."""
    from agent.transport.proposal import normalize_proposal, store_pending

    proposal, display = parse_proposal(text)
    body = display or text
    html_body = _md_to_html(body)
    if proposal:
        try:
            normalize_proposal(proposal)
            proposal_id = store_pending(str(user_id), proposal)
            keyboard = confirm_decline_keyboard(
                confirm_data=f"cfm:{proposal_id}",
                decline_data=f"dec:{proposal_id}",
            )
            await message.answer(html_body, reply_markup=keyboard, parse_mode="HTML")
        except ValueError:
            logger.warning("Skipping confirm buttons for invalid proposal: %s", proposal)
            await message.answer(
                html_body + "\n\n⚠️ Proposal was incomplete — please describe the transaction again.",
                parse_mode="HTML",
            )
    else:
        await message.answer(html_body, parse_mode="HTML")
