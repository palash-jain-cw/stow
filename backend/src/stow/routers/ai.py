from __future__ import annotations

import logging
import time
from datetime import date

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from pydantic_ai import Agent
from sqlmodel import Session, select

from stow.ai_config import read_config, write_config, normalize_base_url, model_settings, resolve_llm_base_url
from stow.ai_agent import get_ai_agent, ParsedTransaction
from stow.db import get_session
from stow.models import Account, Transaction

router = APIRouter(prefix="/ai", tags=["ai"])
logger = logging.getLogger(__name__)


class ConfigOut(BaseModel):
    base_url: str
    model: str


class ConfigIn(BaseModel):
    base_url: str
    model: str
    api_key: str = ""


class ConnectionResult(BaseModel):
    ok: bool
    model: str | None = None
    latency_ms: float | None = None
    error: str | None = None


class ParseRequest(BaseModel):
    text: str


@router.get("/config", response_model=ConfigOut)
def get_config():
    cfg = read_config()
    return ConfigOut(base_url=cfg["base_url"], model=cfg["model"])


@router.post("/config", response_model=ConfigOut)
def post_config(body: ConfigIn):
    write_config(body.base_url, body.model, body.api_key)
    try:
        from agent.transport.telegram.handlers import clear_conversation_history

        clear_conversation_history()
    except Exception:
        logger.exception("Failed to clear Telegram conversation history after LLM config save")
    cfg = read_config()
    return ConfigOut(base_url=cfg["base_url"], model=cfg["model"])


class TestConnectionIn(BaseModel):
    base_url: str = ""
    model: str = ""
    api_key: str = ""


@router.post("/test-connection", response_model=ConnectionResult)
async def test_connection(body: TestConnectionIn = TestConnectionIn()):
    saved = read_config()
    base_url = body.base_url or saved["base_url"]
    model = body.model or saved["model"]
    api_key = body.api_key or saved.get("api_key", "")
    try:
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openai import OpenAIProvider
        from pydantic_ai import Agent
        from stow.ai_config import _DEFAULT_API_KEY, _DEFAULT_BASE_URL, _DEFAULT_MODEL
        effective_url = resolve_llm_base_url(base_url)
        logger.info("Testing LLM connection at %s model=%s", effective_url, model)
        ai_model = OpenAIChatModel(
            model or _DEFAULT_MODEL,
            provider=OpenAIProvider(
                base_url=effective_url,
                api_key=api_key or _DEFAULT_API_KEY,
            ),
        )
        agent = Agent(ai_model)
        start = time.monotonic()
        await agent.run("ping", model_settings=model_settings("ping"))
        latency_ms = (time.monotonic() - start) * 1000
        return ConnectionResult(ok=True, model=model, latency_ms=round(latency_ms, 1))
    except Exception as exc:
        logger.error("LLM test-connection failed: %s", exc, exc_info=True)
        effective_url = resolve_llm_base_url(body.base_url or saved["base_url"])
        return ConnectionResult(
            ok=False,
            error=f"{exc} (resolved url={effective_url})",
        )


@router.post("/parse-transaction", response_model=ParsedTransaction)
async def parse_transaction(
    body: ParseRequest,
    session: Session = Depends(get_session),
    agent: Agent = Depends(get_ai_agent),
):
    accounts = session.exec(select(Account).where(Account.is_archived == False)).all()  # noqa: E712
    recent_txns = session.exec(
        select(Transaction).order_by(Transaction.date.desc()).limit(10)  # type: ignore[attr-defined]
    ).all()

    accounts_ctx = "\n".join(
        f"  id={a.id} name={a.name!r} group_id={a.group_id}" for a in accounts
    )
    txns_ctx = "\n".join(
        f"  date={t.date} type={t.type} narration={t.narration!r}" for t in recent_txns
    )
    user_prompt = (
        f"Today's date: {date.today()}\n\n"
        f"Accounts:\n{accounts_ctx or '  (none)'}\n\n"
        f"Recent transactions:\n{txns_ctx or '  (none)'}\n\n"
        f"Parse: {body.text}"
    )

    result = await agent.run(user_prompt, model_settings=model_settings("parse"))
    return result.output
