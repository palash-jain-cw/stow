# Stow — Personal Accounting System

## What This Is

Stow is a personal double-entry bookkeeping application for a GST-registered salaried individual with occasional freelance income in India. It is not a generic accounting platform — it is scoped tightly to one user's needs: recording transactions, tracking GST/TDS obligations, and generating standard financial reports.

It is not Tally. It is inspired by Tally's accounting model but uses plain English vocabulary and strips away everything unrelated to bookkeeping (no invoicing, no inventory, no payroll).

## Domain Vocabulary

| Term | Meaning |
|---|---|
| **Account** | A named ledger tracking money (e.g. "HDFC Bank", "Electricity Expense", "Output CGST") |
| **Account Group** | A category that accounts belong to (e.g. "Bank Accounts", "Indirect Expenses", "Duties & Taxes") |
| **Transaction** | A complete double-entry record, made up of two or more entries that balance to zero |
| **Entry** | A single debit or credit line within a transaction |
| **Voucher Type** | The nature of a transaction: Payment, Receipt, Journal, or Contra |
| **Financial Year (FY)** | April 1 – March 31. Books are isolated per FY with explicit open/close |
| **Opening Balance** | The balance of an account at the start of a financial year |
| **Narration** | A required free-text description on every transaction (except Contra) |
| **Transaction Audit Log** | The original state of a transaction before any edit; preserved immutably when a posted transaction is modified |
| **Transaction Number** | A human-readable reference in the format `{TYPE}-{YYYY}-{SEQ}` (e.g. `PAY-2024-001`), sequential per transaction type per FY, resets each April 1 |
| **Depreciation Rate** | The WDV rate (per Income Tax Act) on a fixed asset account, used to calculate year-end depreciation (e.g. 40% for computers, 15% for furniture) |
| **Half-Year Rule** | IT Act rule: assets added after October 3 attract 50% of normal depreciation in the year of acquisition |
| **Accumulated Depreciation** | A contra-asset account paired with each fixed asset, holding the total depreciation posted to date |
| **Lot** | A single purchase of an investment: date, units/shares, price per unit — used for FIFO capital gains calculation |
| **Holding** | The set of open lots for a given investment account |
| **STCG** | Short-Term Capital Gain — equity held < 12 months, taxed at 20% |
| **LTCG** | Long-Term Capital Gain — equity held ≥ 12 months, taxed at 12.5% above ₹1.25L exemption |
| **Staging Area** | A temporary holding space for AI-parsed bank statement rows, pending user review and confirmation before being posted as transactions |
| **Price Quote** | A fetched market price for an investment account on a given date — NAV for equity MFs (from AMFI), price for stocks (from NSE/yfinance); used to calculate current value and unrealized gain on the Portfolio screen |
| **Price Source ID** | The identifier used to fetch prices for an investment account — AMFI scheme code for equity MFs, NSE ticker symbol (e.g. `INFY`, `HDFCBANK`) for stocks |
| **Transaction Date** | The date the transaction actually occurred — canonical for all reports |
| **Entry Date** | The date the transaction was recorded in Stow — stored as metadata, never used in reports |
| **Tag** | A free-form label on a transaction for filtering and grouping (e.g. `freelance`, `tax-deductible`) |
| **Merchant Rule** | A saved mapping from a merchant name pattern to an account, applied automatically on future imports |

## Accounting Model

### Double Entry
Every transaction must have entries that sum to zero (debits = credits). This is enforced at the application layer and validated before posting.

### Account Group Hierarchy
Seeded from Tally's standard Indian chart of accounts, fully customizable:

```
Balance Sheet
├── Capital Account
│   ├── Capital
│   └── Reserves & Surplus (Retained Earnings opening balance updated at new FY creation — see ADR 005)
├── Loans (Liability)
│   ├── Bank OD Accounts
│   ├── Secured Loans
│   └── Unsecured Loans
├── Current Liabilities
│   ├── Duties & Taxes          ← GST & TDS accounts live here
│   ├── Credit Cards            ← Credit card liability accounts
│   ├── Sundry Creditors
│   └── Provisions
├── Fixed Assets                ← each account carries a WDV depreciation rate
│   └── Accumulated Depreciation ← contra-asset; one account per fixed asset
├── Investments
└── Current Assets
    ├── Bank Accounts
    ├── Cash-in-Hand
    └── Sundry Debtors

Profit & Loss
├── Income
│   ├── Direct Income           ← Salary, freelance income
│   └── Indirect Income         ← Interest, profit on asset sale
└── Expenses
    ├── Direct Expenses
    └── Indirect Expenses       ← Utilities, subscriptions, etc.
```

### GST Accounts (seeded, under Duties & Taxes)
- Input CGST, Input SGST, Input IGST
- Output CGST, Output SGST, Output IGST

### TDS Accounts (seeded, under Duties & Taxes)
- TDS Receivable (deducted from salary/freelance)
- TDS Payable (if applicable)

### Transaction Types
| Type | Use |
|---|---|
| **Payment** | Money going out of a bank/cash account |
| **Receipt** | Money coming into a bank/cash account |
| **Journal** | General adjusting entry (multi-leg, e.g. asset disposal, depreciation) |
| **Contra** | Transfer between two cash/bank accounts |

### Financial Year Lifecycle
1. **Open** — FY is created, opening balances entered
2. **Active** — transactions can be posted
3. **Locked** — FY is closed, no further edits; net profit calculated and stored on the FY record. Retained Earnings is updated via opening balance carry-forward when the next FY is created (see ADR 005)

### Opening Balances
- Dedicated bulk-entry screen when a new FY is created
- Each account's opening balance is also editable individually until its first transaction is posted

### Investments
Investment accounts are split into four sub-types with different tracking needs:

| Sub-type | Capital Gains | Model |
|---|---|---|
| Equity Mutual Funds | Yes — STCG/LTCG | FIFO lots (units, NAV, date) |
| Direct Stocks | Yes — STCG/LTCG | FIFO lots (shares, price, date) |
| Fixed Deposits | No — interest is income | Principal, rate, maturity date, TDS |
| PPF | No — tax-free | Contribution tracking, balance |
| Real Estate | v2 | — |

- Equity MF and stock accounts maintain a **Holding** (set of open Lots)
- On sale, FIFO lots are consumed and STCG/LTCG calculated automatically
- A **Capital Gains Report** is generated for ITR Schedule CG
- FD interest income is recorded as a Receipt transaction; TDS deducted tracked under TDS Receivable
- PPF contributions recorded as Payment transactions to a PPF asset account

### Live Prices (Equity MF & Stocks)
- Each equity MF account carries an AMFI scheme code (**Price Source ID**); each stock account carries an NSE ticker symbol
- A daily background job fetches current NAV from the AMFI/mfapi.in API and stock prices from NSE bhavcopy or yfinance
- Fetched prices are stored in a `price_quote` table (account, price, date)
- **Current value** = latest price quote × open units; **Unrealized gain** = current value − cost basis
- The Portfolio screen shows current value and unrealized gain only when a price quote exists for the account; otherwise it shows cost basis only

### Depreciation
- Method: Written Down Value (WDV) per Income Tax Act
- Each fixed asset account carries a depreciation rate
- Half-year rule applies: assets added after October 3 get 50% depreciation in year of acquisition
- At year-end, system calculates depreciation amounts per asset and presents them for review
- User posts the Journal entry (never auto-posted): Debit Depreciation Expense → Credit Accumulated Depreciation
- Balance Sheet shows gross cost and accumulated depreciation separately

### Recurring Transactions
- Any transaction type can be set to repeat: Daily, Weekly, Monthly, Yearly
- On the due date, the transaction appears in the Dashboard "Needs attention" zone for review
- User can confirm as-is, edit then confirm, or skip
- If no action is taken by end of day, the transaction auto-posts as-is
- Recurring schedule stored per transaction: frequency, day-of-period, end date (optional)

## Reports

All reports are generated server-side and exportable as PDF.

| Report | Method |
|---|---|
| Trial Balance | Sum of all account balances at a point in time |
| Balance Sheet | Assets = Liabilities + Equity, as of a date |
| Profit & Loss | Income − Expenses for a date range |
| Cash Flow Statement | Indirect method; accounts tagged Operating/Investing/Financing |
| Capital Gains Report | FIFO-based STCG/LTCG breakdown for equity MFs and stocks; for ITR Schedule CG |

### Cash Flow Tagging
- Seed data sets defaults (Bank Accounts → Operating, Fixed Assets → Investing, Loans → Financing)
- Accounts flagged as "investment accounts" at creation are tagged Investing
- Tags are overridable per account

## AI Features

### Natural Language Entry
- User types a loose narrative: "paid electricity bill 2400 from HDFC last Tuesday"
- LLM infers date, amount, voucher type, and account mappings
- Proposed transaction is shown for review and confirmation before posting
- Never auto-posts without user confirmation

### Bank Statement Import
- Supports PDF (text extraction via pdfplumber/pymupdf → LLM parsing) and CSV
- Supported banks: Axis Bank, HDFC, Bank of India, AU Small Finance Bank, Union Bank of India (both bank and credit card statements)
- Parsed rows land in a staging area
- LLM suggests matches against existing transactions (duplicate detection by amount + date proximity)
- User confirms matches and new entries before posting
- Mark-and-match reconciliation: matched rows are marked reconciled

### Merchant Rules
- When a user overrides an AI-suggested account mapping, they are asked "always map this merchant to X?"
- Confirmed rules are saved to a **Merchant Rule** table (merchant pattern → account)
- On future imports, saved rules are applied first; AI fills remaining unmapped rows
- Rules can be managed (viewed, edited, deleted) from settings

### AI Stack
- Any OpenAI-compatible local inference server (oMLX, Ollama, LM Studio, vLLM, etc.)
- Configured via `STOW_LLM_BASE_URL` and `STOW_LLM_MODEL` environment variables
- No external API calls — all inference is on-device

## Technology Stack

| Layer | Choice |
|---|---|
| Frontend | Vite + React + shadcn/ui + React Query |
| Backend | FastAPI (Python) |
| ORM | SQLModel + Alembic |
| Database | PostgreSQL |
| AI | OpenAI-compatible local inference API (oMLX, Ollama, LM Studio, vLLM) |
| PDF export | WeasyPrint or ReportLab |
| PDF parsing | pdfplumber or pymupdf |
| Deployment | Docker Compose (local machine) |

## Project Structure

```
stow/
├── frontend/          # Vite + React SPA
├── backend/           # FastAPI application
│   └── src/stow/      # Python package
├── docs/
│   └── adr/           # Architecture Decision Records
├── docker-compose.yml
└── CONTEXT.md
```

## Key Constraints

- **Single user** — no multi-tenancy, no user table, minimal auth
- **Local only** — runs on developer's machine via Docker Compose
- **INR only** — currency field stubbed for future multi-currency support
- **No invoicing** — bookkeeping only, no GST return generation
- **Indian FY** — April 1 to March 31, hard year boundaries
- **Attachments** — stored on local Docker volume, path saved in DB
