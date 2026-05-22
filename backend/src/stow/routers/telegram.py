from __future__ import annotations

import logging
import traceback

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from stow.db import get_session
from stow.models import TelegramUser
from stow.telegram_config import read_telegram_config, write_telegram_config

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/telegram", tags=["telegram"])


class TelegramConfigOut(BaseModel):
    configured: bool
    bot_username: str | None = None
    enabled: bool
    linked_users: list[dict]


class TelegramConfigIn(BaseModel):
    bot_token: str


class TelegramTestIn(BaseModel):
    bot_token: str = ""


class TelegramTestResult(BaseModel):
    ok: bool
    bot_username: str | None = None
    bot_name: str | None = None
    error: str | None = None


def _linked_users(session: Session) -> list[dict]:
    rows = session.exec(select(TelegramUser)).all()
    return [
        {
            "telegram_user_id": u.telegram_user_id,
            "username": u.username,
        }
        for u in rows
    ]


def _bot_enabled() -> bool:
    from agent.transport.telegram.bot import is_bot_running

    return is_bot_running()


async def _fetch_bot_info(token: str) -> dict:
    url = f"https://api.telegram.org/bot{token}/getMe"
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.get(url)
        r.raise_for_status()
        payload = r.json()
        if not payload.get("ok"):
            raise ValueError(payload.get("description", "Telegram API returned ok=false"))
        return payload["result"]


async def _config_out(session: Session) -> TelegramConfigOut:
    cfg = read_telegram_config()
    token = cfg.get("bot_token", "")
    configured = bool(token)
    bot_username: str | None = None
    if configured:
        try:
            info = await _fetch_bot_info(token)
            bot_username = info.get("username")
        except Exception as exc:
            logger.warning("Could not fetch Telegram bot info: %s", exc)
    return TelegramConfigOut(
        configured=configured,
        bot_username=bot_username,
        enabled=_bot_enabled(),
        linked_users=_linked_users(session),
    )


@router.get("/config", response_model=TelegramConfigOut)
async def get_config(session: Session = Depends(get_session)):
    return await _config_out(session)


@router.post("/config", response_model=TelegramConfigOut)
async def post_config(body: TelegramConfigIn, session: Session = Depends(get_session)):
    from agent.transport.telegram.bot import reload_bot

    token = body.bot_token.strip()
    if not token:
        write_telegram_config("")
        await reload_bot()
        return await _config_out(session)

    try:
        await _fetch_bot_info(token)
    except Exception as exc:
        logger.warning("Rejected invalid Telegram token: %s", traceback.format_exc())
        raise HTTPException(status_code=400, detail=f"Invalid bot token: {exc}") from exc

    write_telegram_config(token)
    started = await reload_bot()
    if not started:
        logger.error("Telegram token saved but bot failed to start polling")
        raise HTTPException(
            status_code=502,
            detail="Token saved but the bot failed to start. Check backend logs and try again.",
        )
    return await _config_out(session)


@router.post("/test-connection", response_model=TelegramTestResult)
async def test_connection(body: TelegramTestIn = TelegramTestIn()):
    saved = read_telegram_config()
    token = (body.bot_token or saved.get("bot_token", "")).strip()
    if not token:
        return TelegramTestResult(ok=False, error="Bot token is required")
    try:
        info = await _fetch_bot_info(token)
        username = info.get("username")
        name = info.get("first_name")
        return TelegramTestResult(ok=True, bot_username=username, bot_name=name)
    except Exception as exc:
        logger.warning("Telegram test connection failed: %s", traceback.format_exc())
        return TelegramTestResult(ok=False, error=str(exc))
