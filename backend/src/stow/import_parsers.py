from __future__ import annotations

import io
import logging
import re
import traceback
from datetime import date, datetime
from typing import Any, Literal

import pymupdf
import pymupdf.layout  # noqa: F401 — enables pymupdf-layout for pymupdf4llm
import pymupdf4llm
from pydantic import BaseModel, Field, model_validator
from pydantic_ai import Agent
from pydantic_ai.messages import BinaryContent

logger = logging.getLogger(__name__)

# Number of PDF pages sent to the LLM per import parse call.
IMPORT_PAGE_BATCH_SIZE = 2

_SKIP_ROW_MARKERS = ("OPENING BALANCE", "CLOSING BALANCE", "TRANSACTION TOTAL")


class DebitCreditTableSchema:
    """Column layout from the first header row of a bank statement table."""

    __slots__ = ("date_idx", "particulars_idx", "debit_idx", "credit_idx")

    def __init__(
        self,
        *,
        date_idx: int | None,
        particulars_idx: int,
        debit_idx: int,
        credit_idx: int,
    ) -> None:
        self.date_idx = date_idx
        self.particulars_idx = particulars_idx
        self.debit_idx = debit_idx
        self.credit_idx = credit_idx


class ParsedRow(BaseModel):
    date: date
    amount_paise: int = Field(
        description="Absolute transaction amount in paise (always a positive integer).",
    )
    flow: Literal["out", "in"] | None = Field(
        default=None,
        description=(
            "'out' = money left the bank account (withdrawal, debit, Dr, payment, UPI send); "
            "'in' = money entered the account (deposit, credit, Cr, salary, refund received)."
        ),
    )
    description: str

    @model_validator(mode="after")
    def normalize_flow_and_amount(self) -> ParsedRow:
        """Accept legacy signed amount_paise from older parser output."""
        if self.flow is not None:
            if self.amount_paise == 0:
                raise ValueError("amount_paise must be non-zero")
            self.amount_paise = abs(self.amount_paise)
            return self
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
You are a bank statement parser. Given markdown extracted from the first one or two pages of a bank \
statement PDF (tables are preserved as markdown pipe tables), identify the bank name and statement \
period (usually on page 1) and parse every transaction row across all pages in this batch.

For each transaction row return:
- date
- description (as shown on the statement)
- amount_paise: absolute amount in paise (INR rupees × 100, always positive)
- flow: "out" or "in" from the account holder's perspective:
  - "out" = money left this bank account (withdrawal, debit, Dr, payment, purchase, UPI/payment sent)
  - "in" = money entered this bank account (deposit, credit, Cr, salary, refund, UPI received)

Indian bank statements often label columns Withdrawal/Debit/Dr vs Deposit/Credit/Cr — use those labels, \
not double-entry bookkeeping sign conventions.

Skip opening/closing balance lines and section totals — only real transaction rows.
You must always return the rows array with every transaction found in this batch (use [] if none).
Respond only with valid JSON matching the required schema.
"""

_CONTINUATION_PAGE_PROMPT = """\
You are a bank statement parser. Given markdown extracted from one or two continuation pages of a bank \
statement (tables are preserved as markdown pipe tables), parse every transaction row in this batch.

For each row return date, description, amount_paise (absolute paise, always positive), and flow:
- "out" = withdrawal / debit / payment leaving the account
- "in" = deposit / credit / receipt into the account

Skip opening/closing balance lines, footers, legal text, and section totals.
Return rows only (use [] if these pages have no transactions).
Respond only with valid JSON matching the required schema.
"""


def _open_pdf_document(file_bytes: bytes) -> pymupdf.Document:
    if not file_bytes.startswith(b"%PDF"):
        raise ValueError("File does not look like a PDF — expected content starting with %PDF")
    try:
        return pymupdf.open(stream=file_bytes, filetype="pdf")
    except Exception as exc:
        logger.error("PDF open failed: %s", traceback.format_exc())
        raise ValueError(f"Could not read PDF: {exc}") from exc


def extract_pdf_page_chunks(file_bytes: bytes) -> list[dict[str, Any]]:
    """Extract per-page markdown chunks via pymupdf4llm + pymupdf-layout."""
    doc = _open_pdf_document(file_bytes)
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


def extract_pdf_page_texts(file_bytes: bytes) -> list[str]:
    """Extract non-empty markdown text from each PDF page separately."""
    chunks = extract_pdf_page_chunks(file_bytes)
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


def _rupees_str_to_paise(value: str) -> int:
    cleaned = value.replace(",", "").strip()
    if not cleaned:
        return 0
    try:
        return round(float(cleaned) * 100)
    except ValueError:
        return 0


def _parse_statement_date(value: str) -> date | None:
    value = value.strip()
    for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%d-%m-%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def _find_column_index(header: list[str], *names: str) -> int | None:
    normalized = [h.replace("\n", " ").strip().lower() for h in header]
    for name in names:
        name_l = name.lower()
        for idx, cell in enumerate(normalized):
            if cell == name_l or name_l in cell:
                return idx
    return None


def _normalize_table_cell(value: str) -> str:
    value = re.sub(r"<br\s*/?>", " ", value, flags=re.I)
    return value.replace("**", "").strip()


def _iter_markdown_tables(text: str) -> list[list[list[str]]]:
    """Split markdown pipe tables into row/cell matrices."""
    tables: list[list[list[str]]] = []
    current: list[list[str]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|"):
            if re.match(r"^\|[-:\s|]+\|$", stripped):
                continue
            cells = [_normalize_table_cell(cell) for cell in stripped.strip("|").split("|")]
            current.append(cells)
            continue
        if current:
            tables.append(current)
            current = []
    if current:
        tables.append(current)
    return tables


def _is_skip_row(cells: list[str]) -> bool:
    joined = " ".join(cells).upper()
    return any(marker in joined for marker in _SKIP_ROW_MARKERS)


def _detect_table_schema(table: list[list[str]]) -> DebitCreditTableSchema | None:
    if not table:
        return None
    header = table[0]
    debit_idx = _find_column_index(header, "debit", "withdrawal")
    credit_idx = _find_column_index(header, "credit", "deposit")
    particulars_idx = _find_column_index(header, "particulars", "description", "narration")
    if debit_idx is None or credit_idx is None or particulars_idx is None:
        return None
    date_idx = _find_column_index(header, "tran date", "date", "value date")
    return DebitCreditTableSchema(
        date_idx=date_idx,
        particulars_idx=particulars_idx,
        debit_idx=debit_idx,
        credit_idx=credit_idx,
    )


def _parse_table_data_rows(
    table: list[list[str]],
    schema: DebitCreditTableSchema,
    *,
    has_header: bool,
) -> list[ParsedRow]:
    """Parse transaction rows using a known debit/credit column layout."""
    rows: list[ParsedRow] = []
    last_date: date | None = None
    start = 1 if has_header else 0

    for raw_cells in table[start:]:
        cells = [cell.strip() for cell in raw_cells]
        if not any(cells) or _is_skip_row(cells):
            continue
        if schema.particulars_idx >= len(cells):
            continue

        particulars = cells[schema.particulars_idx].strip()
        if not particulars or particulars.upper() in _SKIP_ROW_MARKERS:
            continue

        debit_str = cells[schema.debit_idx] if schema.debit_idx < len(cells) else ""
        credit_str = cells[schema.credit_idx] if schema.credit_idx < len(cells) else ""

        if debit_str and credit_str:
            logger.warning(
                "Skipping row with both debit and credit populated: %s",
                particulars,
            )
            continue

        if debit_str:
            amount_paise = _rupees_str_to_paise(debit_str)
            flow: Literal["out", "in"] = "out"
        elif credit_str:
            amount_paise = _rupees_str_to_paise(credit_str)
            flow = "in"
        else:
            continue

        if amount_paise <= 0:
            continue

        txn_date: date | None = None
        if schema.date_idx is not None and schema.date_idx < len(cells):
            txn_date = _parse_statement_date(cells[schema.date_idx])
        if txn_date is None:
            txn_date = last_date
        if txn_date is None:
            logger.warning("Skipping table row without a parseable date: %s", particulars)
            continue
        last_date = txn_date

        rows.append(
            ParsedRow(
                date=txn_date,
                amount_paise=amount_paise,
                flow=flow,
                description=particulars,
            )
        )

    return rows


def _parse_debit_credit_table(
    table: list[list[str]],
    schema: DebitCreditTableSchema | None = None,
) -> tuple[list[ParsedRow], DebitCreditTableSchema | None]:
    """Parse one markdown table; reuse schema for headerless continuation pages."""
    detected = _detect_table_schema(table)
    if detected is not None:
        return _parse_table_data_rows(table, detected, has_header=True), detected
    if schema is None:
        return [], None
    return _parse_table_data_rows(table, schema, has_header=False), schema


def _extract_statement_metadata(full_text: str) -> tuple[str | None, date | None, date | None]:
    bank: str | None = None
    bank_match = re.search(r"Statement of (\w+)\s+Account", full_text, re.I)
    if bank_match:
        name = bank_match.group(1).strip()
        if name.lower() == "axis":
            bank = "Axis Bank"
        elif "bank" in name.lower():
            bank = name
        else:
            bank = f"{name} Bank"

    period_match = re.search(
        r"From:\s*(\d{2}-\d{2}-\d{4})\s*To:\s*(\d{2}-\d{2}-\d{4})",
        full_text,
        re.I,
    )
    statement_from = (
        _parse_statement_date(period_match.group(1)) if period_match else None
    )
    statement_to = (
        _parse_statement_date(period_match.group(2)) if period_match else None
    )
    return bank, statement_from, statement_to


def try_parse_statement_from_tables(file_bytes: bytes) -> ParsedStatement | None:
    """Parse statements with structured Debit/Credit columns from markdown tables."""
    rows: list[ParsedRow] = []
    full_text_parts: list[str] = []
    schema: DebitCreditTableSchema | None = None
    pages_with_tables = 0
    pages_with_rows = 0

    for chunk in extract_pdf_page_chunks(file_bytes):
        text = chunk.get("text") or ""
        full_text_parts.append(text)
        page_row_count = 0
        for table in _iter_markdown_tables(text):
            pages_with_tables += 1
            table_rows, schema = _parse_debit_credit_table(table, schema)
            page_row_count += len(table_rows)
            rows.extend(table_rows)
        if page_row_count:
            pages_with_rows += 1

    if not rows:
        return None

    bank, statement_from, statement_to = _extract_statement_metadata("\n".join(full_text_parts))
    if not statement_from or not statement_to:
        dates = [row.date for row in rows]
        statement_from = statement_from or min(dates)
        statement_to = statement_to or max(dates)

    if not bank:
        bank = "Unknown Bank"

    logger.info(
        "Parsed %d transaction rows from PDF markdown tables for %s "
        "(%d pages with tables, %d pages with rows)",
        len(rows),
        bank,
        pages_with_tables,
        pages_with_rows,
    )
    return ParsedStatement(
        bank=bank,
        statement_from=statement_from,
        statement_to=statement_to,
        rows=rows,
    )


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


# ── Vision-based PDF parsing ──────────────────────────────────────────────

_VISION_FIRST_PAGE_PROMPT = """\
You are an expert at reading bank statements from images. Below is an image of page 1 \
of a bank statement. Your job is to extract every transaction row from the visible table.

For each transaction row return:
- date (DD-MM-YYYY format)
- description (the narration/particulars text)
- amount_paise: absolute amount in paise (INR rupees x 100, always positive integer)
- flow: "out" or "in" from the account holder's perspective:
  - "out" = money left this bank account (withdrawal, debit, Dr, payment, purchase, UPI/payment sent)
  - "in" = money entered this account (deposit, credit, Cr, salary, refund, UPI received)

Indian bank statements often label columns Withdrawal/Debit/Dr vs Deposit/Credit/Cr — use those labels.

Also try to identify:
- bank name (usually at the top)
- statement period (From: ... To: ...)

Skip opening/closing balance lines and section totals — only real transaction rows.
You must always return the rows array (use [] if none).
Respond only with valid JSON matching the required schema.
"""

_VISION_CONTINUATION_PROMPT = """\
You are an expert at reading bank statements from images. Below is an image of a \
continuation page of a bank statement. Parse every transaction row from the visible table.

For each row return date, description, amount_paise (absolute paise, always positive), and flow:
- "out" = withdrawal / debit / payment leaving the account
- "in" = deposit / credit / receipt into the account

Skip opening/closing balance lines, footers, legal text, and section totals.
Return rows only (use [] if these pages have no transactions).
Respond only with valid JSON matching the required schema.
"""


def _render_pdf_pages_as_images(
    file_bytes: bytes,
    dpi: int = 200,
    max_pages: int = 50,
) -> list[bytes]:
    """Render each PDF page as a PNG image (bytes).

    Uses pymupdf (fitz) to rasterize pages at the given DPI.
    Returns a list of PNG image bytes, one per page.
    """
    doc = pymupdf.open(stream=file_bytes, filetype="pdf")
    try:
        images: list[bytes] = []
        for page_num in range(min(len(doc), max_pages)):
            page = doc[page_num]
            # Render at specified DPI for good OCR quality
            pix = page.get_pixmap(dpi=dpi)
            images.append(pix.tobytes("png"))
        return images
    finally:
        doc.close()


def build_vision_parser_agent() -> Agent:
    """Vision-capable LLM agent for parsing bank statement page images."""
    from pydantic_ai.models.openai import OpenAIChatModel
    from pydantic_ai.providers.openai import OpenAIProvider
    from stow.ai_config import build_model, model_settings

    # Use the same model config but with a larger token budget for vision input
    model = build_model()
    # Ensure the model is configured for vision (max_tokens for image context)
    settings = model_settings("import")

    return Agent(
        model,
        output_type=ParsedPage,
        system_prompt=_VISION_FIRST_PAGE_PROMPT,
        output_retries=3,
    )


def build_vision_continuation_agent() -> Agent:
    """Vision-capable LLM agent for continuation page images."""
    from pydantic_ai.models.openai import OpenAIChatModel
    from pydantic_ai.providers.openai import OpenAIProvider
    from stow.ai_config import build_model, model_settings

    model = build_model()
    settings = model_settings("import")

    return Agent(
        model,
        output_type=ParsedPage,
        system_prompt=_VISION_CONTINUATION_PROMPT,
        output_retries=3,
    )


async def _parse_single_page_image(
    image_bytes: bytes,
    *,
    page_number: int,
    page_count: int,
    context: dict[str, str],
    first_page_agent: Agent | None = None,
    continuation_agent: Agent | None = None,
) -> ParsedPage:
    """Send a single page image to the vision LLM and parse transactions."""
    from stow.ai_config import model_settings

    agent = first_page_agent if page_number == 1 else continuation_agent
    if agent is None:
        if page_number == 1:
            agent = build_vision_parser_agent()
        else:
            agent = build_vision_continuation_agent()

    # BinaryContent takes raw bytes; the provider handles encoding
    image_part = BinaryContent(
        data=image_bytes,
        media_type="image/png",
    )

    if page_number == 1:
        prompt_text = "Please parse all transactions from this bank statement page."
    else:
        bank_info = f"Bank: {context.get('bank', 'unknown')}. " if context.get('bank') else ""
        period_info = (
            f"Statement period: {context.get('statement_from', '?')} to "
            f"{context.get('statement_to', '?')}. "
        )
        prompt_text = (
            f"This is page {page_number} of {page_count}. {bank_info}{period_info}"
            f"Please parse all transactions from this bank statement page."
        )

    # Pass a sequence of UserContent (text + image) as user_prompt
    user_prompt_parts: list[Any] = [prompt_text, image_part]

    logger.info(
        "Vision parsing bank statement page %d/%d",
        page_number,
        page_count,
    )

    result = await agent.run(user_prompt_parts, model_settings=model_settings("import"))
    return result.output


async def parse_statement_pdf_vision(
    file_bytes: bytes,
    *,
    dpi: int = 200,
) -> ParsedStatement:
    """Parse a bank statement PDF using vision-based LLM (one image per page).

    Renders each PDF page as an image and sends it to a vision-capable LLM
    for transaction extraction. Pages are processed sequentially, with context
    (bank name, statement period) carried forward from earlier pages.
    """
    images = _render_pdf_pages_as_images(file_bytes, dpi=dpi)
    if not images:
        raise ValueError("No pages could be rendered from this PDF")

    page_count = len(images)
    parsed_pages: list[ParsedPage] = []
    context: dict[str, str] = {}

    first_agent = build_vision_parser_agent()
    cont_agent = build_vision_continuation_agent()

    for idx, image_bytes in enumerate(images):
        page_num = idx + 1
        page = await _parse_single_page_image(
            image_bytes,
            page_number=page_num,
            page_count=page_count,
            context=context,
            first_page_agent=first_agent,
            continuation_agent=cont_agent,
        )
        parsed_pages.append(page)
        _update_context(context, page)

        # Reset first/continuation agent refs after page 1
        if page_num == 1:
            first_agent = None
            cont_agent = build_vision_continuation_agent()

    return merge_parsed_pages(parsed_pages)


def _chunk_page_texts(
    page_texts: list[str],
    batch_size: int = IMPORT_PAGE_BATCH_SIZE,
) -> list[tuple[int, list[str]]]:
    """Split page texts into (start_index, batch_pages) tuples."""
    batches: list[tuple[int, list[str]]] = []
    for start in range(0, len(page_texts), batch_size):
        batches.append((start, page_texts[start : start + batch_size]))
    return batches


def _format_batch_text(page_texts: list[str], start_page_index: int) -> str:
    if len(page_texts) == 1:
        return page_texts[0]
    parts = []
    for offset, text in enumerate(page_texts):
        page_num = start_page_index + offset + 1
        parts.append(f"--- Page {page_num} ---\n{text}")
    return "\n\n".join(parts)


async def _parse_page_batch(
    page_texts: list[str],
    *,
    start_page_index: int,
    page_count: int,
    context: dict[str, str],
    first_page_agent: Agent,
    continuation_agent: Agent,
) -> ParsedPage:
    from stow.ai_config import model_settings

    batch_text = _format_batch_text(page_texts, start_page_index)
    end_page_index = start_page_index + len(page_texts) - 1

    if start_page_index == 0:
        agent = first_page_agent
        prompt = batch_text
    else:
        agent = continuation_agent
        if len(page_texts) == 1:
            page_label = f"Page {start_page_index + 1} of {page_count}"
        else:
            page_label = (
                f"Pages {start_page_index + 1}-{end_page_index + 1} of {page_count}"
            )
        prompt = (
            f"Bank: {context.get('bank', 'unknown')}\n"
            f"Statement period: {context.get('statement_from', '?')} to "
            f"{context.get('statement_to', '?')}\n"
            f"{page_label}.\n\n"
            f"{batch_text}"
        )

    if len(page_texts) == 1:
        logger.info(
            "Parsing bank statement page %d/%d (%d chars)",
            start_page_index + 1,
            page_count,
            len(batch_text),
        )
    else:
        logger.info(
            "Parsing bank statement pages %d-%d/%d (%d chars)",
            start_page_index + 1,
            end_page_index + 1,
            page_count,
            len(batch_text),
        )

    result = await agent.run(prompt, model_settings=model_settings("import"))
    if start_page_index == 0:
        first = result.output
        return ParsedPage(
            bank=first.bank,
            statement_from=first.statement_from,
            statement_to=first.statement_to,
            rows=first.rows,
        )
    cont = result.output
    return ParsedPage(rows=cont.rows)


def _update_context(context: dict[str, str], page: ParsedPage) -> None:
    if page.bank:
        context["bank"] = page.bank
    if page.statement_from:
        context["statement_from"] = page.statement_from.isoformat()
    if page.statement_to:
        context["statement_to"] = page.statement_to.isoformat()


async def parse_statement_pdf(
    file_bytes: bytes,
    first_page_agent: Agent | None = None,
    continuation_agent: Agent | None = None,
    page_batch_size: int = IMPORT_PAGE_BATCH_SIZE,
    *,
    use_vision: bool | None = None,
    vision_dpi: int = 200,
) -> ParsedStatement:
    """Parse a bank statement PDF.

    Strategy (in order):
      1. Structured markdown table parsing (fastest, no LLM)
      2. Vision-based LLM parsing — one image per page (recommended)
      3. Text-based LLM parsing — markdown text batches (fallback)
    """
    # Fast path: extract from markdown tables (no LLM needed)
    table_parsed = try_parse_statement_from_tables(file_bytes)
    if table_parsed is not None:
        return table_parsed

    # Determine whether to use vision mode
    # Default to vision if the configured model name suggests a vision model,
    # otherwise try vision and fall back to text if it fails.
    if use_vision is None:
        from stow.ai_config import read_config
        cfg = read_config()
        model_name = (cfg.get("model") or "").lower()
        use_vision = any(
            marker in model_name
            for marker in ("vl", "vision", "instruct", "qwen2.5-vl", "qwen2-vl")
        )

    if use_vision:
        try:
            return await parse_statement_pdf_vision(file_bytes, dpi=vision_dpi)
        except Exception as exc:
            logger.warning(
                "Vision parsing failed, falling back to text-based: %s",
                exc,
            )
            # Fall through to text-based parsing below

    # Fallback: text-based LLM parsing
    page_texts = extract_pdf_page_texts(file_bytes)
    first = first_page_agent or build_import_parser_agent()
    cont = continuation_agent or build_continuation_parser_agent()

    parsed_pages: list[ParsedPage] = []
    context: dict[str, str] = {}
    page_count = len(page_texts)

    for start_index, batch_texts in _chunk_page_texts(page_texts, page_batch_size):
        page = await _parse_page_batch(
            batch_texts,
            start_page_index=start_index,
            page_count=page_count,
            context=context,
            first_page_agent=first,
            continuation_agent=cont,
        )
        parsed_pages.append(page)
        _update_context(context, page)

    return merge_parsed_pages(parsed_pages)


async def _parse_page_text(
    page_text: str,
    *,
    page_index: int,
    page_count: int,
    context: dict[str, str],
    first_page_agent: Agent,
    continuation_agent: Agent,
) -> ParsedPage:
    """Parse a single page (legacy helper for tests)."""
    return await _parse_page_batch(
        [page_text],
        start_page_index=page_index,
        page_count=page_count,
        context=context,
        first_page_agent=first_page_agent,
        continuation_agent=continuation_agent,
    )


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
