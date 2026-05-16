from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from stow.ai_config import read_config, normalize_base_url


class ParsedTransaction(BaseModel):
    type: Literal["payment", "receipt", "journal", "contra"]
    date: date
    amount: int  # paise
    narration: str
    from_account_id: int
    to_account_id: int
    confidence: float


_SYSTEM_PROMPT = """\
You are an accounting assistant for an Indian personal finance system.
Parse the user's natural language description into a structured transaction.
Return amounts in paise (integer). Resolve account names to IDs from the provided list.
Resolve relative dates (e.g. "last Tuesday") against the current date provided in the prompt.
Respond only with valid JSON matching the required schema.
"""


def build_agent() -> Agent:
    cfg = read_config()
    model = OpenAIChatModel(
        cfg["model"] or "default",
        provider=OpenAIProvider(
            base_url=normalize_base_url(cfg["base_url"]) if cfg["base_url"] else "http://localhost:11434/v1",
            api_key=cfg.get("api_key") or "not-needed",
        ),
    )
    return Agent(model, output_type=ParsedTransaction, system_prompt=_SYSTEM_PROMPT)


def get_ai_agent() -> Agent:
    return build_agent()
