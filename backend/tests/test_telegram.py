from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram import Bot, Dispatcher
from aiogram.types import Message, User
from sqlmodel import Session, select

from stow.models import TelegramUser


# ─── Test 1: create_bot_and_dispatcher returns (None, None) when token not set ───

def test_create_bot_and_dispatcher_no_token(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    from agent.transport.telegram.bot import create_bot_and_dispatcher
    bot, dp = create_bot_and_dispatcher()
    assert bot is None
    assert dp is None


# ─── Test 2: create_bot_and_dispatcher returns (Bot, Dispatcher) when token set ───

def test_create_bot_and_dispatcher_with_token(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:ABC-test-token")
    from agent.transport.telegram.bot import create_bot_and_dispatcher
    bot, dp = create_bot_and_dispatcher()
    assert isinstance(bot, Bot)
    assert isinstance(dp, Dispatcher)


# ─── Test 3: TelegramUser model inserts and retrieves cleanly ───

def test_telegram_user_model(session):
    tg_id = 99999001
    user = TelegramUser(telegram_user_id=tg_id, username="testuser")
    session.add(user)
    session.flush()

    assert user.id is not None
    assert user.telegram_user_id == tg_id
    assert user.username == "testuser"

    found = session.exec(
        select(TelegramUser).where(TelegramUser.telegram_user_id == tg_id)
    ).first()
    assert found is not None
    assert found.username == "testuser"


# ─── Test 4: /start handler upserts TelegramUser (no duplicate on second call) ───

def test_start_handler_upserts_user(session):
    tg_id = 99999002

    # First insert (simulates first /start)
    session.add(TelegramUser(telegram_user_id=tg_id, username="bob"))
    session.flush()

    # Second call updates, not inserts (simulates /start again)
    existing = session.exec(
        select(TelegramUser).where(TelegramUser.telegram_user_id == tg_id)
    ).first()
    assert existing is not None
    existing.username = "bob_v2"
    session.flush()

    users = session.exec(
        select(TelegramUser).where(TelegramUser.telegram_user_id == tg_id)
    ).all()
    assert len(users) == 1
    assert users[0].username == "bob_v2"


# ─── Helper: build a fake Message ───

def _make_message(text: str | None = None, tg_id: int = 42, username: str = "alice") -> MagicMock:
    msg = MagicMock(spec=Message)
    msg.text = text
    msg.photo = None
    msg.document = None
    msg.caption = None
    msg.from_user = MagicMock(spec=User)
    msg.from_user.id = tg_id
    msg.from_user.username = username
    msg.answer = AsyncMock()
    msg.bot = AsyncMock()
    return msg


def _find_handler(dp: Dispatcher, name: str):
    """Return the callback registered under the given function name."""
    for handler in dp.message.handlers:
        if handler.callback.__name__ == name:
            return handler.callback
    return None


# ─── Test 5: text handler calls orchestrator and answers with result ───

@pytest.mark.asyncio
async def test_text_handler_calls_orchestrator():
    mock_run = AsyncMock(return_value="₹850 logged")

    with patch("agent.transport.telegram.handlers._get_orchestrator_runner", return_value=mock_run):
        import agent.transport.telegram.handlers as h_mod
        dp = Dispatcher()
        h_mod.register_handlers(dp)

        handle_message = _find_handler(dp, "handle_message")
        assert handle_message is not None

        msg = _make_message(text="paid ₹850 for Zomato")
        await handle_message(msg)

    mock_run.assert_called_once_with("paid ₹850 for Zomato")
    msg.answer.assert_called_once_with("₹850 logged")


# ─── Test 6: /help handler replies without hitting orchestrator ───

@pytest.mark.asyncio
async def test_help_handler_does_not_call_orchestrator():
    mock_run = AsyncMock(return_value="should not be called")

    with patch("agent.transport.telegram.handlers._get_orchestrator_runner", return_value=mock_run):
        import agent.transport.telegram.handlers as h_mod
        dp = Dispatcher()
        h_mod.register_handlers(dp)

        cmd_help = _find_handler(dp, "cmd_help")
        assert cmd_help is not None

        msg = _make_message()
        await cmd_help(msg)

    mock_run.assert_not_called()
    msg.answer.assert_called_once()
    reply_text: str = msg.answer.call_args[0][0]
    assert "/balance" in reply_text


# ─── Test 7: /balance command sends "/balance" prompt to orchestrator ───

@pytest.mark.asyncio
async def test_balance_command_sends_prompt():
    mock_run = AsyncMock(return_value="HDFC: ₹12,000")

    with patch("agent.transport.telegram.handlers._get_orchestrator_runner", return_value=mock_run):
        import agent.transport.telegram.handlers as h_mod
        dp = Dispatcher()
        h_mod.register_handlers(dp)

        cmd_balance = _find_handler(dp, "cmd_balance")
        assert cmd_balance is not None

        msg = _make_message()
        await cmd_balance(msg)

    mock_run.assert_called_once_with("/balance")
    msg.answer.assert_called_once_with("HDFC: ₹12,000")
