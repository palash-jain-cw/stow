from __future__ import annotations

import asyncio
import base64
import logging
import os

import httpx
from fastapi import WebSocket, WebSocketDisconnect
from pydantic_ai.messages import BinaryContent, ModelMessage

from agent.activity import _progress_queue
from agent.deps import StowDeps
from agent.orchestrator import build_orchestrator

logger = logging.getLogger(__name__)


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
            return ["Process this UPI payment screenshot", BinaryContent(data=file_bytes, media_type=mime_type)]
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


async def _drain_progress(queue: asyncio.Queue[str | None], websocket: WebSocket) -> None:
    """Forward progress labels from the queue to the WebSocket until sentinel None arrives."""
    while True:
        label = await queue.get()
        if label is None:
            break
        try:
            await websocket.send_json({"type": "progress", "label": label})
        except Exception:
            pass


async def handle_websocket(websocket: WebSocket) -> None:
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

                active_orchestrator = build_orchestrator()

                queue: asyncio.Queue[str | None] = asyncio.Queue()
                token = _progress_queue.set(queue)
                drain = asyncio.create_task(_drain_progress(queue, websocket))
                try:
                    result = await active_orchestrator.run(
                        prompt, deps=deps, message_history=message_history,
                        model_settings={"max_tokens": 4096},
                    )
                    output = str(result.output).strip()
                    if output:
                        await websocket.send_json({"type": "token", "content": output})
                    message_history = result.all_messages()
                except Exception as exc:
                    print(f"[WS] exception: {type(exc).__name__}: {exc}", flush=True)
                    await websocket.send_json({
                        "type": "token",
                        "content": f"⚠️ Something went wrong — {exc}",
                    })
                finally:
                    await queue.put(None)
                    await drain
                    _progress_queue.reset(token)

                await websocket.send_json({"type": "done"})
        except WebSocketDisconnect:
            pass
