from __future__ import annotations

import asyncio
import logging
import traceback
from datetime import date
from typing import Any, Literal

import pymupdf
import pymupdf.layout  # noqa: F401 — enables pymupdf-layout for pymupdf4llm
import pymupdf4llm
from pydantic import BaseModel, Field, model_validator
from pydantic_ai import Agent

logger = logging.getLogger(__name__)


class ParsedRow(BaseModel):
    date: date
    amount_paise: int = Field(
        description=(
            "Transaction amount in paise (INR × 100). "
            "NEGATIVE when money leaves the account (debit/withdrawal/payment). "
            "POSITIVE when money enters (credit/deposit/received)."
        ),
    )
    flow: Literal["out", "in"] | None = Field(default=None, exclude=True)
    description: str

    @model_validator(mode="after")
    def infer_flow_from_sign(self) -> ParsedRow:
        if self.flow is not None:
            # Explicit flow (Python callers / fixtures): trust it, ensure positive amount.
            if self.amount_paise == 0:
                raise ValueError("amount_paise must be non-zero")
            self.amount_paise = abs(self.amount_paise)
            return self
        # LLM output: flow is absent, infer direction from the sign of amount_paise.
        if self.amount_paise < 0:
            self.flow = "out"
            self.amount_paise = abs(self.amount_paise)
        elif self.amount_paise > 0:
            self.flow = "in"
        else:
            raise ValueError("amount_paise must be non-zero")
        return self

    @property
    def signed_amount_paise(self) -> int:
        """Bank-account view: outflows negative, inflows positive."""
        assert self.flow is not None
        return -self.amount_paise if self.flow == "out" else self.amount_paise


class ParsedStatement(BaseModel):
    bank: str
    statement_from: date
    statement_to: date
    rows: list[ParsedRow]


class ParsedPage(BaseModel):
    """LLM output for one PDF page (optional metadata for continuation pages)."""

    bank: str | None = None
    statement_from: date | None = None
    statement_to: date | None = None
    rows: list[ParsedRow] = Field(default_factory=list)


class ParsedFirstPage(BaseModel):
    """Alias kept for tests — page 1 uses ParsedStatement directly."""

    bank: str
    statement_from: date
    statement_to: date
    rows: list[ParsedRow] = Field(default_factory=list)


class ParsedContinuationPage(BaseModel):
    """LLM output for pages 2+ — transaction rows only."""

    rows: list[ParsedRow] = Field(default_factory=list)


_FIRST_PAGE_PROMPT = """\
You are a bank statement parser. Given markdown extracted from the first page(s) of an Indian bank \
statement PDF (tables are preserved as markdown pipe tables), identify the bank name and statement \
period and parse every transaction row.

For each transaction row return:
- date
- description (as shown on the statement)
- amount_paise: the transaction amount in paise (INR × 100).
  Use a NEGATIVE number when money LEFT the account (Debit / Withdrawal / Dr / payment sent / UPI out).
  Use a POSITIVE number when money ENTERED the account (Credit / Deposit / Cr / received / refund).

Rules:
- If the statement has separate Debit and Credit columns, the Debit column → negative, Credit column → positive.
- If the statement has a single signed Amount column, preserve its sign.
- Some banks pack multiple rows into one table cell using line breaks — treat each as a separate transaction.
- Skip opening/closing balance lines and section totals.
- Return rows: [] if no transactions appear on this page.
Respond only with valid JSON matching the required schema.
"""

_CONTINUATION_PAGE_PROMPT = """\
You are a bank statement parser. Given markdown extracted from continuation page(s) of an Indian bank \
statement PDF, parse every transaction row.

For each row return date, description, and amount_paise (paise = INR × 100):
- NEGATIVE when money LEFT the account (Debit / Withdrawal / Dr / payment sent)
- POSITIVE when money ENTERED the account (Credit / Deposit / Cr / received / refund)

If the statement has separate Debit and Credit columns, Debit → negative, Credit → positive.
Some banks pack multiple rows per cell using line breaks — treat each as a separate transaction.
Skip balance lines, footers, and section totals.
Return rows: [] if no transactions appear on this page.
Respond only with valid JSON matching the required schema.
"""


def _open_pdf_document(file_bytes: bytes, password: str | None = None) -> pymupdf.Document:
    if not file_bytes.startswith(b"%PDF"):
        raise ValueError("File does not look like a PDF — expected content starting with %PDF")
    try:
        doc = pymupdf.open(stream=file_bytes, filetype="pdf")
    except Exception as exc:
        logger.error("PDF open failed: %s", traceback.format_exc())
        raise ValueError(f"Could not read PDF: {exc}") from exc
    if doc.needs_pass:
        if not password:
            raise ValueError("This PDF is password-protected — provide the password to import it")
        if not doc.authenticate(password):
            raise ValueError("Incorrect password for this PDF")
    return doc


def extract_pdf_page_chunks(file_bytes: bytes, password: str | None = None) -> list[dict[str, Any]]:
    """Extract per-page markdown chunks via pymupdf4llm + pymupdf-layout."""
    doc = _open_pdf_document(file_bytes, password)
    try:
        chunks = pymupdf4llm.to_markdown(
            doc,
            page_chunks=True,
            header=False,
            footer=False,
        )
    except Exception as exc:
        logger.error("PDF markdown extraction failed: %s", traceback.format_exc())
        raise ValueError(f"Could not extract text from PDF: {exc}") from exc
    finally:
        doc.close()

    if not isinstance(chunks, list):
        return [{"text": str(chunks), "metadata": {"page_number": 1}}]
    return chunks


def extract_pdf_page_texts(file_bytes: bytes, password: str | None = None) -> list[str]:
    """Extract non-empty markdown text from each PDF page separately."""
    chunks = extract_pdf_page_chunks(file_bytes, password)
    pages = [(chunk.get("text") or "").strip() for chunk in chunks]
    non_empty = [text for text in pages if text]
    if not non_empty:
        raise ValueError("No text could be extracted from this PDF (it may be scanned/image-only)")
    logger.info(
        "Extracted markdown from %d/%d PDF pages via pymupdf4llm (%d total chars)",
        len(non_empty),
        len(pages),
        sum(len(t) for t in non_empty),
    )
    return non_empty


def extract_pdf_text(file_bytes: bytes) -> str:
    """Extract all page text as one string (legacy helper)."""
    return "\n\n".join(extract_pdf_page_texts(file_bytes))


def merge_parsed_pages(pages: list[ParsedPage]) -> ParsedStatement:
    """Combine per-page parse results into one statement."""
    if not pages:
        raise ValueError("No pages were parsed")

    bank = next((p.bank for p in pages if p.bank), None)
    statement_from = next((p.statement_from for p in pages if p.statement_from), None)
    statement_to = next((p.statement_to for p in pages if p.statement_to), None)

    rows: list[ParsedRow] = []
    for page in pages:
        rows.extend(page.rows)

    if not rows:
        raise ValueError("No transaction rows found in the statement")

    if not statement_from or not statement_to:
        dates = [row.date for row in rows]
        statement_from = statement_from or min(dates)
        statement_to = statement_to or max(dates)
        logger.info(
            "Inferred statement period from row dates: %s to %s",
            statement_from,
            statement_to,
        )

    if not bank:
        bank = "Unknown Bank"
        logger.warning("Bank name not detected — using placeholder")

    logger.info(
        "Merged %d pages into %d transaction rows for %s",
        len(pages),
        len(rows),
        bank,
    )
    return ParsedStatement(
        bank=bank,
        statement_from=statement_from,
        statement_to=statement_to,
        rows=rows,
    )


def build_import_parser_agent() -> Agent:
    """LLM agent for the first page of a bank statement."""
    from stow.ai_config import build_model

    return Agent(
        build_model(),
        output_type=ParsedStatement,
        system_prompt=_FIRST_PAGE_PROMPT,
        output_retries=3,
    )


def build_continuation_parser_agent() -> Agent:
    """LLM agent for statement pages after the first."""
    from stow.ai_config import build_model

    return Agent(
        build_model(),
        output_type=ParsedContinuationPage,
        system_prompt=_CONTINUATION_PAGE_PROMPT,
        output_retries=3,
    )


def get_import_parser_agent() -> Agent:
    return build_import_parser_agent()


def _render_pdf_pages_as_images(
    file_bytes: bytes,
    dpi: int = 200,
    max_pages: int = 50,
) -> list[bytes]:
    """Render each PDF page as a PNG image (bytes) using pymupdf."""
    doc = pymupdf.open(stream=file_bytes, filetype="pdf")
    try:
        images: list[bytes] = []
        for page_num in range(min(len(doc), max_pages)):
            page = doc[page_num]
            pix = page.get_pixmap(dpi=dpi)
            images.append(pix.tobytes("png"))
        return images
    finally:
        doc.close()


async def parse_statement_pdf(
    file_bytes: bytes,
    first_page_agent: Agent | None = None,
    continuation_agent: Agent | None = None,
    *,
    password: str | None = None,
) -> ParsedStatement:
    """Parse a bank statement PDF by running each page through the LLM in parallel.

    Page 1 uses the first-page agent (extracts bank name, period, and rows).
    All remaining pages use the continuation agent (rows only) and run concurrently.
    """
    from stow.ai_config import model_settings

    page_texts = extract_pdf_page_texts(file_bytes, password)
    first = first_page_agent or build_import_parser_agent()
    cont = continuation_agent or build_continuation_parser_agent()
    page_count = len(page_texts)

    async def _parse_one(idx: int, text: str) -> ParsedPage:
        if idx == 0:
            result = await first.run(text, model_settings=model_settings("import"))
            out = result.output
            return ParsedPage(
                bank=out.bank,
                statement_from=out.statement_from,
                statement_to=out.statement_to,
                rows=out.rows,
            )
        prompt = f"Page {idx + 1} of {page_count}.\n\n{text}"
        result = await cont.run(prompt, model_settings=model_settings("import"))
        return ParsedPage(rows=result.output.rows)

    logger.info("Parsing %d PDF pages in parallel", page_count)
    parsed_pages = await asyncio.gather(*(_parse_one(i, t) for i, t in enumerate(page_texts)))
    return merge_parsed_pages(list(parsed_pages))


async def _parse_page_text(
    page_text: str,
    *,
    page_index: int,
    page_count: int,
    context: dict[str, str],
    first_page_agent: Agent,
    continuation_agent: Agent,
) -> ParsedPage:
    """Parse a single page (legacy helper for parse_statement)."""
    from stow.ai_config import model_settings

    if page_index == 0:
        result = await first_page_agent.run(page_text, model_settings=model_settings("import"))
        out = result.output
        return ParsedPage(
            bank=out.bank,
            statement_from=out.statement_from,
            statement_to=out.statement_to,
            rows=out.rows,
        )
    prompt = (
        f"Bank: {context.get('bank', 'unknown')}\n"
        f"Statement period: {context.get('statement_from', '?')} to "
        f"{context.get('statement_to', '?')}\n"
        f"Page {page_index + 1} of {page_count}.\n\n"
        f"{page_text}"
    )
    result = await continuation_agent.run(prompt, model_settings=model_settings("import"))
    return ParsedPage(rows=result.output.rows)


async def parse_statement(pdf_text: str, agent: Agent | None = None) -> ParsedStatement:
    """Parse a single text blob as one page (tests and legacy callers)."""
    first = agent or build_import_parser_agent()
    cont = build_continuation_parser_agent()
    page = await _parse_page_text(
        pdf_text,
        page_index=0,
        page_count=1,
        context={},
        first_page_agent=first,
        continuation_agent=cont,
    )
    return merge_parsed_pages([page])
