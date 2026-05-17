from __future__ import annotations

import base64
import os

import httpx
from fastapi import WebSocket, WebSocketDisconnect
from pydantic_ai import Agent
from pydantic_ai.messages import BinaryContent, ModelMessage

from agent.deps import StowDeps


def _build_prompt(data: dict) -> str | list:
    """Convert an incoming WebSocket message (text or image) into a pydantic_ai prompt.

    PDFs are NOT handled here — they are pre-uploaded in handle_websocket before this is called.
    """
    msg_type = data.get("type", "text")
    content = data.get("content", "")

    if msg_type == "file":
        file_bytes = base64.b64decode(content)
        mime_type = data.get("mime_type", "application/octet-stream")
        if mime_type.startswith("image/"):
            return [BinaryContent(data=file_bytes, media_type=mime_type), "Process this UPI payment screenshot"]
        return "Unsupported file type. Please send an image or a bank statement PDF."

    return content


async def _upload_pdf_to_batch(
    file_bytes: bytes,
    fname: str,
    http_client: httpx.AsyncClient,
    base_url: str,
) -> str:
    """Upload a PDF to POST /imports and return an IMPORT_BATCH prompt for the orchestrator."""
    try:
        r = await http_client.post(
            f"{base_url}/imports",
            files={"file": (fname, file_bytes, "application/pdf")},
        )
        r.raise_for_status()
        batch = r.json()
        return (
            f"[IMPORT_BATCH:{batch['id']}:{fname}] "
            f"Bank statement parsed — {batch['row_count']} rows ready for review."
        )
    except Exception as exc:
        return f"Sorry, I couldn't parse the bank statement PDF ({exc}). Please try again."


async def handle_websocket(websocket: WebSocket, orchestrator: Agent) -> None:
    await websocket.accept()
    message_history: list[ModelMessage] = []

    async with httpx.AsyncClient(timeout=120.0) as http_client:
        deps = StowDeps(
            base_url=os.environ.get("STOW_BASE_URL", "http://localhost:8000"),
            http_client=http_client,
        )
        try:
            while True:
                data = await websocket.receive_json()
                msg_type = data.get("type", "text")
                mime_type = data.get("mime_type", "")
                fname = data.get("filename", "statement.pdf")
                if msg_type == "file" and not mime_type.startswith("image/"):
                    file_bytes = base64.b64decode(data.get("content", ""))
                    prompt = await _upload_pdf_to_batch(file_bytes, fname, http_client, deps.base_url)
                else:
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
