"""WebSocket chat transport — TDD tests for issue #27."""
from __future__ import annotations

import base64
from unittest.mock import patch

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel

from agent.deps import StowDeps
from stow.main import app
from tests.helpers import get_or_create_account, get_or_create_fy, get_or_create_group

_ORCH_PATCH = "agent.transport.websocket.build_orchestrator"


@pytest.fixture(autouse=True)
def ws_inprocess_api(monkeypatch):
    """Route WebSocket proposal confirm posts through the test ASGI app, not localhost:8000."""

    class _InProcessClient(AsyncClient):
        def __init__(self, *args, **kwargs):
            kwargs.pop("timeout", None)
            super().__init__(
                transport=ASGITransport(app=app),
                base_url="http://test",
                timeout=120.0,
            )

    monkeypatch.setattr("agent.transport.websocket.httpx.AsyncClient", _InProcessClient)


@pytest.fixture()
def fy(client):
    return get_or_create_fy(client, "2026-04-01", "2027-03-31", status="active")


@pytest.fixture()
def payment_accounts(client):
    get_or_create_group(client, "Bank Accounts", "asset")
    get_or_create_group(client, "Indirect Expenses", "expense")
    return {
        "bank": get_or_create_account(client, "Chat Test Bank", "Bank Accounts"),
        "expense": get_or_create_account(client, "Chat Test Expense", "Indirect Expenses"),
    }


def _test_orchestrator() -> Agent:
    return Agent(model=TestModel(), deps_type=StowDeps, output_type=str)


class TestWebSocketChat:
    def test_websocket_connection_accepted(self, client):
        """WebSocket endpoint accepts and cleanly closes a connection."""
        with patch(_ORCH_PATCH, return_value=_test_orchestrator()):
            with client.websocket_connect("/chat/ws"):
                pass

    def test_text_message_gets_response(self, client):
        """Text message round-trip: user sends text, receives token stream then done."""
        with patch(_ORCH_PATCH, return_value=_test_orchestrator()):
            with client.websocket_connect("/chat/ws") as ws:
                ws.send_json({"type": "text", "content": "hello"})

                messages = []
                while True:
                    msg = ws.receive_json()
                    messages.append(msg)
                    if msg.get("type") == "done":
                        break

                types = {m["type"] for m in messages}
                assert "done" in types
                assert "token" in types or "message" in types
                assert messages[-1]["type"] == "done"

    def test_multi_turn_conversation(self, client):
        """Second message in the same session gets a response (history preserved)."""
        with patch(_ORCH_PATCH, return_value=_test_orchestrator()):
            with client.websocket_connect("/chat/ws") as ws:
                # Turn 1
                ws.send_json({"type": "text", "content": "hello"})
                while ws.receive_json().get("type") != "done":
                    pass
                # Turn 2
                ws.send_json({"type": "text", "content": "and another thing"})
                messages = []
                while True:
                    msg = ws.receive_json()
                    messages.append(msg)
                    if msg.get("type") == "done":
                        break
                assert messages[-1]["type"] == "done"
                assert any(m["type"] == "token" for m in messages)

    def test_disconnection_mid_conversation_is_graceful(self, client):
        """Client that disconnects after sending (no response consumed) raises no server error."""
        with patch(_ORCH_PATCH, return_value=_test_orchestrator()):
            with client.websocket_connect("/chat/ws") as ws:
                ws.send_json({"type": "text", "content": "hello"})
                # close without reading the response — server must not crash

    def test_image_file_message_gets_response(self, client):
        """Base64-encoded image is accepted and the orchestrator responds."""
        image_bytes = b"\x89PNG fake image bytes"
        b64 = base64.b64encode(image_bytes).decode()

        with patch(_ORCH_PATCH, return_value=_test_orchestrator()):
            with client.websocket_connect("/chat/ws") as ws:
                ws.send_json({"type": "file", "content": b64, "mime_type": "image/png"})

                messages = []
                while True:
                    msg = ws.receive_json()
                    messages.append(msg)
                    if msg.get("type") == "done":
                        break

                assert messages[-1]["type"] == "done"

    def test_pdf_file_message_directs_to_import_page(self, client):
        """Web chat rejects PDF uploads and points users to the Bank Import page."""
        pdf_bytes = b"%PDF-1.4 fake pdf content"
        b64 = base64.b64encode(pdf_bytes).decode()

        with client.websocket_connect("/chat/ws") as ws:
            ws.send_json({
                "type": "file",
                "content": b64,
                "mime_type": "application/pdf",
                "filename": "statement.pdf",
            })

            messages = []
            while True:
                msg = ws.receive_json()
                messages.append(msg)
                if msg.get("type") == "done":
                    break

            assert messages[-1]["type"] == "done"
            body = "".join(m["content"] for m in messages if m.get("type") == "token")
            assert "Bank Import" in body


class TestUploadPdfToBatch:
    """Unit tests for _upload_pdf_to_batch."""

    @pytest.mark.asyncio
    async def test_returns_import_batch_prompt_on_success(self):
        """Successful upload returns an [IMPORT_BATCH:...] prompt string."""
        from unittest.mock import AsyncMock, MagicMock
        from agent.transport.websocket import _upload_pdf_to_batch

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"id": 7, "row_count": 42}

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        result = await _upload_pdf_to_batch(b"%PDF fake", "hdfc.pdf", mock_client, "http://test")

        assert "[IMPORT_BATCH:7:hdfc.pdf]" in result
        assert "42" in result

    @pytest.mark.asyncio
    async def test_returns_error_message_on_failure(self):
        """Failed upload returns a user-friendly error string."""
        from unittest.mock import AsyncMock
        from agent.transport.websocket import _upload_pdf_to_batch

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=Exception("connection refused"))

        result = await _upload_pdf_to_batch(b"bad", "x.pdf", mock_client, "http://test")

        assert isinstance(result, str)
        assert "sorry" in result.lower() or "couldn't" in result.lower()

    def test_pdf_websocket_message_does_not_call_upload(self, client):
        """WebSocket PDF messages must not invoke _upload_pdf_to_batch."""
        from unittest.mock import patch

        pdf_bytes = b"%PDF-1.4 fake"
        b64 = base64.b64encode(pdf_bytes).decode()

        with patch("agent.transport.websocket._upload_pdf_to_batch") as mock_upload:
            with client.websocket_connect("/chat/ws") as ws:
                ws.send_json({
                    "type": "file",
                    "content": b64,
                    "mime_type": "application/pdf",
                    "filename": "stmt.pdf",
                })
                while ws.receive_json().get("type") != "done":
                    pass

            mock_upload.assert_not_called()


class TestBuildPrompt:
    """Unit tests for _build_prompt in websocket.py."""

    def test_image_returns_binary_content_with_text_hint(self):
        """Image file produces [BinaryContent, str] so the LLM sees both image and instruction."""
        from pydantic_ai.messages import BinaryContent
        from agent.transport.websocket import _build_prompt

        image_bytes = b"\x89PNG fake image"
        b64 = base64.b64encode(image_bytes).decode()
        result = _build_prompt({"type": "file", "content": b64, "mime_type": "image/png"})

        assert isinstance(result, list)
        binary_parts = [p for p in result if isinstance(p, BinaryContent)]
        assert len(binary_parts) == 1
        assert binary_parts[0].data == image_bytes
        assert binary_parts[0].media_type == "image/png"
        text_parts = [p for p in result if isinstance(p, str)]
        assert len(text_parts) == 1
        assert "screenshot" in text_parts[0].lower()

    def test_non_image_file_returns_unsupported_message(self):
        """Non-image file (e.g. PDF via _build_prompt directly) returns unsupported message.

        PDFs are handled by _upload_pdf_to_batch in handle_websocket, not by _build_prompt.
        This test confirms _build_prompt has a safe fallback for that path.
        """
        from agent.transport.websocket import _build_prompt

        pdf_bytes = b"%PDF-1.4 content"
        b64 = base64.b64encode(pdf_bytes).decode()
        result = _build_prompt({
            "type": "file",
            "content": b64,
            "mime_type": "application/pdf",
            "filename": "statement.pdf",
        })

        assert isinstance(result, str)
        assert "unsupported" in result.lower() or "pdf" in result.lower()

    def test_text_returns_content_string(self):
        """Plain text message returns the content string unchanged."""
        from agent.transport.websocket import _build_prompt

        result = _build_prompt({"type": "text", "content": "hello"})
        assert result == "hello"


class TestImportChatHelpers:
    def test_extract_import_batch_id(self):
        from agent.transport.websocket import _extract_import_batch_id

        assert _extract_import_batch_id("[IMPORT_BATCH:42:stmt.pdf] parsed") == 42
        assert _extract_import_batch_id("hello") is None

    def test_wrap_import_continuation(self):
        from agent.transport.websocket import _wrap_import_continuation

        wrapped = _wrap_import_continuation(7, "confirm anyway")
        assert "[IMPORT_CONTINUATION:batch_id=7]" in wrapped
        assert "confirm anyway" in wrapped

    def test_strip_import_done(self):
        from agent.transport.websocket import _strip_import_done

        text = "IMPORT_DONE:9\n\nPosted 3 transactions."
        cleaned, batch_id = _strip_import_done(text)
        assert batch_id == 9
        assert "IMPORT_DONE" not in cleaned
        assert "Posted 3 transactions" in cleaned


class TestWebSocketConfirmFlow:
    """Confirm / decline short-circuit on the chat WebSocket."""

    def test_confirm_json_posts_without_orchestrator(self, client, fy, payment_accounts):
        """UI Confirm button sends confirm:{json} — posts directly, no LLM."""
        import json

        from_acc = payment_accounts["bank"]
        to_acc = payment_accounts["expense"]

        proposal = {
            "type": "payment",
            "date": "2026-05-22",
            "amount_paise": 199,
            "narration": "ws confirm json test",
            "from_account_id": from_acc["id"],
            "from_account_name": from_acc["name"],
            "to_account_id": to_acc["id"],
            "to_account_name": to_acc["name"],
            "fy_id": fy["id"],
        }

        with client.websocket_connect("/chat/ws") as ws:
            ws.send_json({"type": "text", "content": f"confirm:{json.dumps(proposal)}"})
            tokens = []
            while True:
                msg = ws.receive_json()
                if msg.get("type") == "token":
                    tokens.append(msg["content"])
                if msg.get("type") == "done":
                    break
            body = "".join(tokens)
            assert "Posted" in body or "PAY-" in body

    def test_plain_confirm_after_proposal(self, client, fy, payment_accounts):
        """Typed 'confirm' uses pending proposal stored on the same WebSocket session."""
        import json
        from unittest.mock import patch

        from pydantic_ai import Agent
        from pydantic_ai.models.test import TestModel

        from_acc = payment_accounts["bank"]
        to_acc = payment_accounts["expense"]

        proposal = {
            "type": "payment",
            "date": "2026-05-22",
            "amount_paise": 201,
            "narration": "plain confirm test",
            "from_account_id": from_acc["id"],
            "from_account_name": from_acc["name"],
            "to_account_id": to_acc["id"],
            "to_account_name": to_acc["name"],
            "fy_id": fy["id"],
        }
        orch_out = f"PROPOSAL:{json.dumps(proposal)}\n\nReply confirm to post."

        def fake_orch():
            return Agent(
                model=TestModel(custom_output_text=orch_out),
                deps_type=StowDeps,
                output_type=str,
            )

        with patch(_ORCH_PATCH, fake_orch):
            with client.websocket_connect("/chat/ws") as ws:
                ws.send_json({"type": "text", "content": "record payment"})
                while ws.receive_json().get("type") != "done":
                    pass
                ws.send_json({"type": "text", "content": "confirm"})
                tokens = []
                while True:
                    msg = ws.receive_json()
                    if msg.get("type") == "token":
                        tokens.append(msg["content"])
                    if msg.get("type") == "done":
                        break
                body = "".join(tokens)
                assert "Posted" in body or "PAY-" in body

    def test_decline_short_circuits(self, client):
        """Decline does not invoke the orchestrator."""
        with client.websocket_connect("/chat/ws") as ws:
            ws.send_json({"type": "text", "content": "decline"})
            tokens = []
            while True:
                msg = ws.receive_json()
                if msg.get("type") == "token":
                    tokens.append(msg["content"])
                if msg.get("type") == "done":
                    break
            assert "".join(tokens) == "Transaction discarded."
