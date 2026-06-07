from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field
from pydantic_ai import Agent

from stow.ai_config import build_model


class ParsedTransaction(BaseModel):
    type: Literal["payment", "receipt", "journal", "contra"]
    date: date
    amount: int  # paise
    narration: str
    from_account_id: int
    to_account_id: int
    confidence: float
    tags: list[str] = Field(default_factory=list)


class ParsedTransactionBatch(BaseModel):
    transactions: list[ParsedTransaction]


_SYSTEM_PROMPT = """\
You are an accounting assistant for an Indian personal finance system.
Parse the user's natural language description into structured transactions.

## Single vs Multiple Transactions
- If the user describes ONE transaction, return a list with one item.
- If the user describes MULTIPLE transactions (e.g. "paid electricity 2400, water 800, internet 1200"),
  parse ALL of them into a list. Look for repeated patterns of payee + amount + account/date.
- If you're unsure whether the input contains one or multiple transactions, default to one.

## Rules
- Return amounts in paise (integer). Resolve account names to IDs from the provided list.
- Resolve relative dates (e.g. "last Tuesday") against the current date provided in the prompt.
- When the user mentions tags or labels (e.g. "tag it salary and acme"), include them in tags.
- Use lowercase single-word or short hyphenated tags when possible. Omit tags when none are mentioned.
- Respond only with valid JSON matching the required schema.
"""


def build_agent() -> Agent:
    return Agent(build_model(), output_type=ParsedTransactionBatch, system_prompt=_SYSTEM_PROMPT)


def get_ai_agent() -> Agent:
    return build_agent()
