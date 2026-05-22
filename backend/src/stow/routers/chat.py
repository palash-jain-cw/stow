from __future__ import annotations

from fastapi import APIRouter, WebSocket

router = APIRouter(prefix="/chat", tags=["chat"])


@router.websocket("/ws")
async def chat_ws(websocket: WebSocket) -> None:
    from agent.transport.websocket import handle_websocket

    await handle_websocket(websocket)
