# ADR 003 — AI Integration

**Status:** Accepted

## Context

Two AI-assisted workflows are required at launch: natural language transaction entry and bank statement import. All inference must run locally.

## Decisions

### Natural Language Entry
User provides a loose narrative (e.g. "paid electricity bill 2400 from HDFC last Tuesday"). The LLM infers voucher type, date, amount, and account mappings. The proposed transaction is presented for confirmation before posting. Auto-posting without review is explicitly disallowed.

### Bank Statement Import Pipeline
1. User uploads PDF or CSV for a supported bank
2. PDF: text extracted via pdfplumber/pymupdf, passed to LLM for structured parsing
3. CSV: parsed directly into staging rows
4. LLM maps each row to a proposed transaction with suggested account assignments
5. Duplicate detection: flag rows matching existing transactions by amount + date proximity
6. Mark-and-match reconciliation: user confirms matches; matched rows marked reconciled, unmatched become new transactions

### Supported Banks at Launch
Axis Bank, HDFC, Bank of India, AU Small Finance Bank, Union Bank of India.

### PDF Parsing Strategy
Text extraction + LLM (not vision/multimodal). Bank statement PDFs have a clean text layer; text extraction is more reliable and cheaper than image-based parsing for structured tabular data.

### Suggest-and-Confirm Principle
No AI output is posted to the books without explicit user confirmation. This applies to both natural language entry and bank statement import. Accounting errors are difficult to unwind.

## Rejected Alternatives

- **Vision/multimodal PDF parsing**: text extraction is more reliable for structured bank statement tables
- **Auto-posting AI-generated transactions**: too risky; user confirmation is mandatory
- **External LLM APIs (Claude, OpenAI)**: user prefers local inference for privacy and cost
- **Bank statement import only (no natural language)**: both features needed at launch
