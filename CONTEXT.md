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
| Fixed Deposits | No — interest is income | Principal, rate (bps), maturity date, compounding (simple/monthly/quarterly/yearly) |
| Real Estate | v2 | — |

- Equity MF and stock accounts maintain a **Holding** (set of open Lots)
- Lot units are stored as **milliunits** (1 unit = 1,000 milliunits); cost per unit in paise per milliunit
- On sale, FIFO lots are consumed and STCG/LTCG calculated automatically
- STCG/LTCG tax rates are managed via a versioned **Capital Gains Tax Rule** table (not hardcoded), allowing rates to be updated when legislation changes
- A **Capital Gains Report** is generated for ITR Schedule CG
- FD interest income is recorded as a Receipt transaction; TDS deducted tracked under TDS Receivable
- PPF is out of scope

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

### Conversational Agent Architecture
All user-facing AI interactions flow through a **multi-agent system**:

- **Orchestrator** (`backend/src/agent/orchestrator.py`) — the top-level pydantic_ai agent. Receives all user messages (text, images, PDF references), classifies intent, and delegates to specialised subagents.
- **Subagents** (`backend/src/agent/subagents/`) — each is a focused pydantic_ai agent with its own tool set:
  | Subagent | Responsibility |
  |---|---|
  | `transaction` | NL → create / query / edit / delete transactions |
  | `account` | Create / query / archive accounts |
  | `import_agent` | Bank statement staging row review and bulk confirmation |
  | `investment` | FD, equity MF, stock buy/sell, portfolio queries |
  | `recurring` | Create / confirm / skip recurring schedules |
  | `report` | P&L, balance sheet, cash flow, capital gains queries |

### Transport Layers
- **WebSocket** (`backend/src/agent/transport/websocket.py`) — web chat, real-time token streaming, handles text / image (`BinaryContent`) / PDF uploads. PDFs are pre-uploaded to `POST /imports` before the orchestrator sees them; orchestrator receives `[IMPORT_BATCH:{id}:{filename}]`.
- **Telegram** (`backend/src/agent/transport/telegram/`) — same orchestrator, separate entry point. Handles photo messages as `BinaryContent` for vision, PDF documents as import batches.

### Natural Language Transaction Entry
- User types a loose narrative: "paid electricity bill 2400 from HDFC last Tuesday"
- Orchestrator delegates to transaction subagent; LLM infers date, amount, voucher type, and account mappings
- A **Proposal Card** is shown for review and confirmation before posting
- Never auto-posts without user confirmation

### UPI Screenshot (Vision)
- User sends a UPI payment screenshot via web chat or Telegram
- Orchestrator passes `BinaryContent` to the LLM vision model
- LLM extracts: merchant name, amount, reference number
- `_get_merchant_rules` tool called to pre-fill payee account from saved merchant rules
- Proposal Card shown; user confirms to post

### Bank Statement PDF Import
- Supported: PDF only (text extraction via pdfplumber/pymupdf → LLM parsing)
- Supported banks: Axis Bank, HDFC, Bank of India, AU Small Finance Bank, Union Bank of India (bank and credit card statements)
- User attaches PDF in web chat or Telegram → transport layer uploads to `POST /imports` → batch created with staging rows
- Orchestrator receives `[IMPORT_BATCH:{id}:{filename}]` and delegates to `import_agent`
- `import_agent` resolves bank account and FY using `_list_accounts` / `_get_active_fy` tools; guides user through row-by-row review
- Merchant rules applied automatically; AI suggests accounts for unmapped rows
- User confirms batch → `POST /imports/{id}/confirm` → bulk transaction creation

### Merchant Rules
- Saved mappings from merchant name pattern (substring, case-insensitive, supports `*` wildcard) → account
- Applied automatically during imports and UPI screenshot processing
- Managed from Settings → Merchant Rules (view, edit, delete, undo-on-delete toast)

### Background Scheduler
- APScheduler 4.x running in the FastAPI process, timezone: Asia/Kolkata (IST)
- Jobs: daily price fetch (equity MF NAV + stock prices) and recurring transaction queue population
- Management API at `/scheduler/jobs` — list jobs, trigger manually

### AI Stack
- Any OpenAI-compatible local inference server (oMLX, Ollama, LM Studio, vLLM, etc.)
- LLM client: `pydantic_ai.Agent` wrapping the OpenAI-compatible inference server
- LLM config stored in DB and editable at runtime via Settings → AI / LLM (no restart required)
- `normalize_base_url()` in `backend/src/stow/ai_config.py` rewrites `localhost` → `host.docker.internal` for Docker
- Configured via `STOW_LLM_BASE_URL` and `STOW_LLM_MODEL` environment variables (overridden by DB config if set)
- No external API calls — all inference is on-device

## Telegram Bot

The Telegram bot provides natural-language accounting via the same backend. It complements the web app — quick interactions via bot, deep work via web.

### Design Decisions

| Decision | Choice |
|---|---|
| Scope | Complements web app — no need to replicate full web UX in bot |
| User model | Single user, simple `telegram_user_id` → `user_id` mapping on `/start` |
| Setup | Simple `/start` mapping — no auth flow needed |
| Interaction | Hybrid — free text for daily use, slash commands for specific workflows (`/import`, `/recurring`) |
| Parsing | Single centralized LLM call handles all extraction (amount, type, accounts, date, counterparty) |
| Confirmation | Always show proposal card, never auto-post |
| Editing | Inline keyboard with tapable field buttons (account, date, amount) |
| Account selection | Learns counterparty→account pairings, pre-fills, shows top 3-5 for override |
| Query responses | One-line answer by default, [breakdown] and [report] buttons for detail |
| Screenshots | New `POST /ai/process-image` endpoint using LLM vision capability |
| Bank import | Auto-confirm all staging rows except `possible_duplicate=True` flagged rows |
| Recurring | Daily digest at fixed time, individual [Confirm] [Skip] buttons per item |
| Architecture | Same FastAPI process, shared DB session, uses existing background scheduler |
| State management | In-memory dict keyed by `telegram_user_id`, TTL 10 minutes |
| Error handling | 3 retries with exponential backoff on transient errors, user-friendly messages on failure |
| Financial year | Always checks active FY from backend — no stale state |
| Bot framework | `aiogram 3.x` — async-native, integrates with FastAPI ecosystem |
| AI infrastructure | Reuses existing `pydantic_ai` agent — same LLM provider, same config |

### Bot Vocabulary

| Term | Meaning |
|---|---|
| **Proposal Card** | A scannable summary of the parsed transaction shown before posting — amount, type, accounts, date, narration |
| **Staging Row** | A parsed bank statement line awaiting confirmation — same as web app's staging area |
| **Daily Digest** | A single message listing all recurring transactions due today, with individual [Confirm] [Skip] buttons |
| **Counterparty** | The entity on the other side of a transaction (merchant, person, bank) — extracted from text, UPI ID, or image |

### Bot State Machine

```
idle → parsing → reviewing → editing → confirming → posted
                          ↓
                    editing (loop back to reviewing)
                    editing (cancel → idle)
```

- State stored in-memory, keyed by `telegram_user_id`
- TTL: 10 minutes of inactivity
- On timeout or restart: state is lost, user starts fresh

### File Structure

```
backend/src/
├── agent/
│   ├── orchestrator.py            # Top-level pydantic_ai agent; routes to subagents
│   ├── deps.py                    # Shared dependency injection (DB session, HTTP client)
│   ├── subagents/
│   │   ├── transaction.py         # NL → create/query/edit/delete transactions
│   │   ├── account.py             # Create/query/archive accounts
│   │   ├── import_agent.py        # PDF staging row review and bulk confirmation
│   │   ├── investment.py          # FD, equity MF, stock buy/sell, portfolio
│   │   ├── recurring.py           # Create/confirm/skip recurring schedules
│   │   └── report.py              # P&L, BS, cash flow, capital gains queries
│   └── transport/
│       ├── websocket.py           # Web chat — streaming WebSocket, image/PDF pre-upload
│       ├── proposal.py            # Proposal card formatter (shared across transports)
│       └── telegram/
│           ├── bot.py             # aiogram Bot instance + dispatcher setup
│           ├── handlers.py        # All Telegram event handlers (text, photo, document, commands)
│           └── keyboard.py        # Inline keyboard builders (Confirm/Decline/Edit)
└── stow/
    ├── routers/                   # FastAPI route modules (one per domain)
    ├── models.py                  # SQLModel ORM models
    ├── ai_config.py               # LLM config load/save + normalize_base_url()
    ├── import_pipeline.py         # PDF parsing → staging rows
    ├── import_parsers.py          # Per-bank PDF parsers
    ├── recurring.py               # Queue generation logic
    ├── scheduler.py               # APScheduler job definitions
    ├── reports/                   # Report generation + PDF export
    └── investments/               # FD, lot tracking, capital gains, prices
```

## Technology Stack

| Layer | Choice |
|---|---|
| Frontend | Vite + React 19 + TanStack Query v5 + lucide-react (no component library — custom design system) |
| Backend | FastAPI (Python) |
| ORM | SQLModel + Alembic |
| Database | PostgreSQL |
| AI | pydantic_ai + OpenAI-compatible local inference (oMLX, Ollama, LM Studio, vLLM) |
| Scheduler | APScheduler 4.x (IST timezone) |
| PDF export | WeasyPrint or ReportLab |
| PDF parsing | pdfplumber or pymupdf |
| Deployment | Docker Compose (local machine) |
| Telegram Bot | aiogram 3.x (async-native, same FastAPI process) |

## Project Structure

```
stow/
├── frontend/          # Vite + React SPA
│   └── src/
│       ├── pages/     # Dashboard, Transactions, Accounts, Reports, Portfolio, Settings, Onboarding
│       └── components/# Sidebar, ChatSidebar, TransactionEntrySheet, ProposalCard, AccountSheet, …
├── backend/           # FastAPI application
│   └── src/
│       ├── agent/     # Orchestrator + subagents + transport layers (WebSocket, Telegram)
│       └── stow/      # FastAPI app, routers, models, reports, investments, scheduler
├── docs/
│   └── adr/           # Architecture Decision Records
├── QA_CHECKLIST.md    # Comprehensive manual QA checklist (all user-facing features)
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
