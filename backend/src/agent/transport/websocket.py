from __future__ import annotations

import asyncio
import base64
import logging
import os
import re
import traceback

import httpx
from fastapi import WebSocket, WebSocketDisconnect
from pydantic_ai.messages import BinaryContent, ModelMessage

from agent.activity import _progress_queue
from agent.deps import StowDeps
from agent.history import trim_message_history
from agent.orchestrator import build_orchestrator
from agent.transport.proposal import (
    handle_proposal_action,
    normalize_proposal,
    parse_proposal,
    store_pending,
)
from stow.ai_config import model_settings

logger = logging.getLogger(__name__)

_IMPORT_BATCH_RE = re.compile(r"^\[IMPORT_BATCH:(\d+):")
_IMPORT_CONTINUATION_PREFIX = "[IMPORT_CONTINUATION:batch_id="
_IMPORT_DONE_PREFIX = "IMPORT_DONE:"


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
        bank_hint = f" Detected bank: {batch['detected_bank']}." if batch.get("detected_bank") else ""
        return (
            f"[IMPORT_BATCH:{batch['id']}:{fname}] "
            f"Bank statement parsed — {batch['row_count']} rows ready for review.{bank_hint}"
        )
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text[:500] if exc.response is not None else str(exc)
        logger.error(
            "Bank statement PDF upload failed for %s: HTTP %s %s\n%s",
            fname,
            exc.response.status_code if exc.response is not None else "?",
            detail,
            traceback.format_exc(),
        )
        if exc.response is not None and exc.response.status_code == 422:
            try:
                body = exc.response.json()
                msg = body.get("detail", detail)
            except Exception:
                msg = detail
            return f"Sorry, I couldn't parse the bank statement PDF — {msg}"
        return f"Sorry, I couldn't parse the bank statement PDF ({exc}). Please try again."
    except Exception as exc:
        logger.error(
            "Bank statement PDF upload failed for %s: %s",
            fname,
            traceback.format_exc(),
        )
        return f"Sorry, I couldn't parse the bank statement PDF ({exc}). Please try again."


def _extract_import_batch_id(prompt: str) -> int | None:
    match = _IMPORT_BATCH_RE.match(prompt.strip())
    if not match:
        return None
    return int(match.group(1))


def _wrap_import_continuation(batch_id: int, prompt: str) -> str:
    return (
        f"{_IMPORT_CONTINUATION_PREFIX}{batch_id}] "
        f"Continue the in-progress bank import for batch {batch_id}. User reply: {prompt}"
    )


def _strip_import_done(output: str) -> tuple[str, int | None]:
    """Remove IMPORT_DONE:{batch_id} marker; return cleaned text and batch id if present."""
    lines = output.splitlines()
    remaining: list[str] = []
    done_batch_id: int | None = None
    for line in lines:
        if line.startswith(_IMPORT_DONE_PREFIX):
            raw_id = line[len(_IMPORT_DONE_PREFIX):].strip()
            try:
                done_batch_id = int(raw_id)
            except ValueError:
                logger.warning("Invalid IMPORT_DONE batch id: %s", raw_id)
            continue
        remaining.append(line)
    return "\n".join(remaining).strip(), done_batch_id


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
    session_key = f"ws:{id(websocket)}"
    active_import_batch_id: int | None = None

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
                    logger.info("Web chat rejected non-image upload: %s", fname)
                    await websocket.send_json({
                        "type": "token",
                        "content": (
                            "Bank statement PDFs are imported via **Bank Import** in the sidebar "
                            "(upload → review rows → confirm). Chat supports UPI payment screenshots only."
                        ),
                    })
                    await websocket.send_json({"type": "done"})
                    continue
                prompt = _build_prompt(data)

                if isinstance(prompt, str):
                    batch_id = _extract_import_batch_id(prompt)
                    if batch_id is not None:
                        active_import_batch_id = batch_id
                        logger.info("Started import chat session for batch_id=%s", batch_id)
                    elif active_import_batch_id is not None:
                        prompt = _wrap_import_continuation(active_import_batch_id, prompt)

                    action = await handle_proposal_action(
                        prompt,
                        http_client,
                        deps.base_url,
                        user_key=session_key,
                    )
                    if action.kind == "reply":
                        await websocket.send_json({"type": "token", "content": action.message})
                        await websocket.send_json({"type": "done"})
                        continue
                    if action.kind == "agent":
                        prompt = action.message
                        if active_import_batch_id is not None:
                            prompt = _wrap_import_continuation(active_import_batch_id, prompt)

                message_history = trim_message_history(message_history)
                active_orchestrator = build_orchestrator()

                queue: asyncio.Queue[str | None] = asyncio.Queue()
                token = _progress_queue.set(queue)
                drain = asyncio.create_task(_drain_progress(queue, websocket))
                try:
                    result = await active_orchestrator.run(
                        prompt,
                        deps=deps,
                        message_history=message_history,
                        model_settings=model_settings("orchestrator"),
                    )
                    output = str(result.output).strip()
                    if output:
                        output, import_done_id = _strip_import_done(output)
                        if import_done_id is not None:
                            logger.info(
                                "Import chat session complete for batch_id=%s",
                                import_done_id,
                            )
                            active_import_batch_id = None
                        proposal, _ = parse_proposal(output)
                        if proposal is not None:
                            try:
                                normalize_proposal(proposal)
                                store_pending(session_key, proposal)
                            except ValueError:
                                logger.warning(
                                    "Orchestrator returned incomplete proposal: %s", proposal
                                )
                        if output:
                            await websocket.send_json({"type": "token", "content": output})
                    message_history = trim_message_history(result.all_messages())
                except Exception as exc:
                    logger.exception("WebSocket orchestrator failed")
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
