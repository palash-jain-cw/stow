from __future__ import annotations

import os
from io import BytesIO
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

    mock_run.assert_called_once_with("paid ₹850 for Zomato", msg.from_user.id)
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

    mock_run.assert_called_once_with("/balance", msg.from_user.id)
    msg.answer.assert_called_once_with("HDFC: ₹12,000")


# ─── Test 8: photo handler builds a BinaryContent prompt ───

@pytest.mark.asyncio
async def test_photo_handler_builds_binary_content_prompt():
    """Telegram photo produces a [BinaryContent, str] prompt, not [IMAGE:b64] text."""
    from pydantic_ai.messages import BinaryContent

    captured: dict = {}

    async def mock_run(prompt, user_id):
        captured["prompt"] = prompt
        captured["user_id"] = user_id
        return "ok"

    with patch("agent.transport.telegram.handlers._get_orchestrator_runner", return_value=mock_run):
        import agent.transport.telegram.handlers as h_mod
        dp = Dispatcher()
        h_mod.register_handlers(dp)

        handle_message = _find_handler(dp, "handle_message")
        assert handle_message is not None

        fake_bytes = b"\xff\xd8\xff JPEG data"
        msg = _make_message()
        msg.photo = [MagicMock()]
        msg.caption = "Paid Zomato"
        msg.bot.get_file = AsyncMock(return_value=MagicMock(file_path="photos/x.jpg"))
        msg.bot.download_file = AsyncMock(return_value=BytesIO(fake_bytes))

        await handle_message(msg)

    prompt = captured["prompt"]
    assert isinstance(prompt, list), "prompt must be a list for multimodal"
    binary_parts = [p for p in prompt if isinstance(p, BinaryContent)]
    assert len(binary_parts) == 1
    assert binary_parts[0].data == fake_bytes
    assert binary_parts[0].media_type == "image/jpeg"
    text_parts = [p for p in prompt if isinstance(p, str)]
    assert text_parts[0] == "Paid Zomato"


@pytest.mark.asyncio
async def test_pdf_handler_builds_import_batch_prompt():
    """Telegram PDF handler pre-uploads and produces an [IMPORT_BATCH:...] prompt."""
    captured: dict = {}

    async def mock_run(prompt, user_id):
        captured["prompt"] = prompt
        return "ok"

    async def fake_upload(file_bytes, fname, http_client, base_url):
        return f"[IMPORT_BATCH:3:{fname}] Statement parsed."

    with patch("agent.transport.telegram.handlers._get_orchestrator_runner", return_value=mock_run):
        with patch("agent.transport.websocket._upload_pdf_to_batch", side_effect=fake_upload):
            import agent.transport.telegram.handlers as h_mod
            dp = Dispatcher()
            h_mod.register_handlers(dp)

            handle_message = _find_handler(dp, "handle_message")

            msg = _make_message()
            msg.photo = None
            doc = MagicMock()
            doc.file_name = "statement.pdf"
            doc.file_id = "doc123"
            msg.document = doc
            msg.bot.get_file = AsyncMock(return_value=MagicMock(file_path="files/x.pdf"))
            msg.bot.download_file = AsyncMock(return_value=BytesIO(b"%PDF fake"))

            await handle_message(msg)

    assert captured["prompt"].startswith("[IMPORT_BATCH:3:statement.pdf]")


@pytest.mark.asyncio
async def test_photo_handler_uses_default_caption_when_none():
    """Photo without a caption uses a default instruction string."""
    from pydantic_ai.messages import BinaryContent

    captured: dict = {}

    async def mock_run(prompt, user_id):
        captured["prompt"] = prompt
        return "ok"

    with patch("agent.transport.telegram.handlers._get_orchestrator_runner", return_value=mock_run):
        import agent.transport.telegram.handlers as h_mod
        dp = Dispatcher()
        h_mod.register_handlers(dp)

        handle_message = _find_handler(dp, "handle_message")

        msg = _make_message()
        msg.photo = [MagicMock()]
        msg.caption = None
        msg.bot.get_file = AsyncMock(return_value=MagicMock(file_path="photos/x.jpg"))
        msg.bot.download_file = AsyncMock(return_value=BytesIO(b"\xff\xd8"))

        await handle_message(msg)

    text_parts = [p for p in captured["prompt"] if isinstance(p, str)]
    assert len(text_parts) == 1
    assert len(text_parts[0]) > 0
