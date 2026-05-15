from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

import pdfplumber
from pydantic import BaseModel
from pydantic_ai import Agent

if TYPE_CHECKING:
    from io import BytesIO


class ParsedRow(BaseModel):
    date: date
    amount_paise: int
    description: str


class ParsedStatement(BaseModel):
    bank: str
    statement_from: date
    statement_to: date
    rows: list[ParsedRow]


_SYSTEM_PROMPT = """\
You are a bank statement parser. Given raw text extracted from a bank statement PDF,
identify the bank name, statement period, and parse every transaction row.
Return amounts in paise (integer). Debits are negative, credits are positive.
Respond only with valid JSON matching the required schema.
"""


def extract_pdf_text(file_bytes: bytes) -> str:
    import io
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        return "\n".join(
            page.extract_text() or "" for page in pdf.pages
        )


async def parse_statement(agent: Agent, pdf_text: str) -> ParsedStatement:
    result = await agent.run(pdf_text)
    return result.data
