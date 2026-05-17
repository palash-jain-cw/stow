from __future__ import annotations

import base64
import os

import httpx
from fastapi import WebSocket, WebSocketDisconnect
from pydantic_ai import Agent
from pydantic_ai.messages import BinaryContent, ModelMessage

from agent.deps import StowDeps


def _build_prompt(data: dict) -> str | list:
    """Convert an incoming WebSocket message into a pydantic_ai prompt."""
    msg_type = data.get("type", "text")
    content = data.get("content", "")

    if msg_type == "file":
        file_bytes = base64.b64decode(content)
        mime_type = data.get("mime_type", "application/octet-stream")
        if mime_type.startswith("image/"):
            return [BinaryContent(data=file_bytes, media_type=mime_type)]
        # PDF/other: pass as a text prompt — import_agent handles the base64
        fname = data.get("filename", "document")
        return f"[PDF:{content}:{fname}] Import this bank statement"

    return content


async def handle_websocket(websocket: WebSocket, orchestrator: Agent) -> None:
    await websocket.accept()
    message_history: list[ModelMessage] = []

    async with httpx.AsyncClient(timeout=60.0) as http_client:
        deps = StowDeps(
            base_url=os.environ.get("STOW_BASE_URL", "http://localhost:8000"),
            http_client=http_client,
        )
        try:
            while True:
                data = await websocket.receive_json()
                prompt = _build_prompt(data)

                try:
                    async with orchestrator.run_stream(
                        prompt, deps=deps, message_history=message_history
                    ) as result:
                        async for chunk in result.stream_text(delta=True):
                            await websocket.send_json({"type": "token", "content": chunk})

                    message_history = result.all_messages()
                except Exception:
                    await websocket.send_json({
                        "type": "token",
                        "content": "⚠️ Something went wrong — please try again.",
                    })

                await websocket.send_json({"type": "done"})
        except WebSocketDisconnect:
            pass
