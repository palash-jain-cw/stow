# ADR 014 — Bank Import & Merchant Rules

**Status:** Accepted

## Context

Issue #12: full bank statement import pipeline — upload PDF → extract text → LLM parses rows → stage for review → post. Plus merchant rules that short-circuit AI suggestions for known merchants.

## Decisions

### Models

**`ImportBatch`** — tracks an uploaded statement file.
Fields: id, filename, uploaded_at, detected_bank (nullable), statement_from, statement_to, bank_account_id (nullable), status (`processing` / `ready` / `posted`)

**`StagingRow`** — one row from a parsed statement, pending user review.
Fields: id, batch_id, raw_data (JSON), date, amount (paise — negative = debit), description, suggested_account_id (nullable), status (`pending` / `confirmed` / `discarded` / `reconciled`), matched_transaction_id (nullable), narration_override (nullable), tags (JSON array), possible_duplicate (bool, default False)

**`MerchantRule`** — wildcard pattern → account mapping saved by the user.
Fields: id, pattern (wildcard, case-insensitive), account_id

### PDF Parsing Pipeline

1. pdfplumber extracts all table text from the uploaded PDF as a plain string
2. Single LLM call via pydantic-ai: result type `ParsedStatement` (Pydantic model)
   - `bank: str`, `statement_from: date`, `statement_to: date`
   - `rows: list[ParsedRow]` — each row: `date, amount_paise (int), description`
3. No per-bank adapters — LLM handles all format variation
4. No CSV support at launch

### Account Mapping (priority order)

1. Merchant rule — `fnmatch.fnmatch(description.lower(), pattern.lower())`
2. LLM batch call — single call with full account list + all unmapped descriptions
3. `suggested_account_id = None` if neither matches

### Duplicate Detection

After parsing rows: for each `StagingRow`, query `Entry` joined with `Transaction` where `Entry.amount = row.amount` and `Transaction.date` is within ±1 day. Sets `possible_duplicate = True` if any match found. Does not block confirmation.

### `POST /imports/{id}/confirm`

For each `StagingRow` with `status = "confirmed"`:
- Creates one `Transaction` + two `Entry` records (debit + credit)
- `from_account_id` = `bank_account_id` from the batch (for debits) or `suggested_account_id`
- Saves any merchant rules the user selected (via a `rules_to_save` field on the request)
- Marks batch `status = "posted"`

### Processing Model

Synchronous within the request — statement files are small enough. `status` field preserved for future async upgrade.

### File Structure

```
stow/import_parsers.py     — extract_pdf_text(), parse_statement() (LLM call), ParsedStatement/ParsedRow
stow/import_pipeline.py    — detect_duplicates(), map_accounts(), confirm_batch()
stow/models.py             — ImportBatch, StagingRow, MerchantRule added
stow/routers/imports.py    — upload + staging area endpoints
stow/routers/merchant_rules.py
tests/test_imports.py
```

### TDD Slices

1. Models — 3 new tables can be created and queried
2. Merchant rule wildcard matching — `fnmatch` logic, case-insensitive
3. Duplicate detection — exact match, ±1 day, no false positive on different amount
4. `POST /imports` — PDF upload → LLM parses → batch + staging rows created (LLM mocked)
5. Account mapping — merchant rule takes priority over LLM suggestion
6. `GET /imports/{id}` + `GET /imports/{id}/rows`
7. `PUT /imports/{id}/rows/{row_id}` — update status / account / narration
8. `POST /imports/{id}/rows/{row_id}/match` — reconcile to existing transaction
9. `POST /imports/{id}/confirm` — confirmed rows become posted transactions
10. Merchant rules CRUD

## Rejected Alternatives

- **CSV adapters per bank**: removed — LLM handles format variation uniformly
- **pymupdf**: pdfplumber has simpler table-extraction API for structured bank statement tables
- **Regex for merchant matching**: `fnmatch` wildcards are simpler and match the UX (`BESCOM*`)
- **Async background processing**: deferred; sync is sufficient for statement file sizes
