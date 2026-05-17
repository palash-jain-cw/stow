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
