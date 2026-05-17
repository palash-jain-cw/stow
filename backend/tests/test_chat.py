"""WebSocket chat transport — TDD tests for issue #27."""
from __future__ import annotations

import base64
from unittest.mock import patch

from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel

from agent.deps import StowDeps


def _test_orchestrator() -> Agent:
    return Agent(model=TestModel(), deps_type=StowDeps, output_type=str)


class TestWebSocketChat:
    def test_websocket_connection_accepted(self, client):
        """WebSocket endpoint accepts and cleanly closes a connection."""
        with patch("stow.routers.chat.build_orchestrator", return_value=_test_orchestrator()):
            with client.websocket_connect("/chat/ws"):
                pass

    def test_text_message_gets_response(self, client):
        """Text message round-trip: user sends text, receives token stream then done."""
        with patch("stow.routers.chat.build_orchestrator", return_value=_test_orchestrator()):
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
        with patch("stow.routers.chat.build_orchestrator", return_value=_test_orchestrator()):
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
        with patch("stow.routers.chat.build_orchestrator", return_value=_test_orchestrator()):
            with client.websocket_connect("/chat/ws") as ws:
                ws.send_json({"type": "text", "content": "hello"})
                # close without reading the response — server must not crash

    def test_image_file_message_gets_response(self, client):
        """Base64-encoded image is accepted and the orchestrator responds."""
        image_bytes = b"\x89PNG fake image bytes"
        b64 = base64.b64encode(image_bytes).decode()

        with patch("stow.routers.chat.build_orchestrator", return_value=_test_orchestrator()):
            with client.websocket_connect("/chat/ws") as ws:
                ws.send_json({"type": "file", "content": b64, "mime_type": "image/png"})

                messages = []
                while True:
                    msg = ws.receive_json()
                    messages.append(msg)
                    if msg.get("type") == "done":
                        break

                assert messages[-1]["type"] == "done"

    def test_pdf_file_message_gets_response(self, client):
        """Base64-encoded PDF is accepted and the orchestrator responds."""
        pdf_bytes = b"%PDF-1.4 fake pdf content"
        b64 = base64.b64encode(pdf_bytes).decode()

        with patch("stow.routers.chat.build_orchestrator", return_value=_test_orchestrator()):
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

    def test_pdf_returns_text_prompt(self):
        """PDF file produces a plain text prompt with [PDF:...] prefix."""
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
        assert result.startswith("[PDF:")
        assert "statement.pdf" in result

    def test_text_returns_content_string(self):
        """Plain text message returns the content string unchanged."""
        from agent.transport.websocket import _build_prompt

        result = _build_prompt({"type": "text", "content": "hello"})
        assert result == "hello"
