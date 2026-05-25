# Stow - Personal Accounting System

## What This Is

Stow is a personal double-entry bookkeeping application for a GST-registered salaried individual with occasional freelance income in India. It is not a generic accounting platform - it is scoped tightly to one user's needs: recording transactions, tracking GST/TDS obligations, and generating standard financial reports.

It is not Tally. It is inspired by Tally's accounting model but uses plain English vocabulary and strips away everything unrelated to bookkeeping (no invoicing, no inventory, no payroll).

## Domain Vocabulary

| Term | Meaning |
|---|---|
| **Account** | A named ledger tracking money (e.g. "HDFC Bank", "Electricity Expense", "Output CGST") |
| **Account Group** | A category that accounts belong to (e.g. "Bank Accounts", "Indirect Expenses", "Duties & Taxes") |
| **Transaction** | A complete double-entry record, made up of two or more entries that balance to zero |
| **Entry** | A single debit or credit line within a transaction |
| **Voucher Type** | The nature of a transaction: Payment, Receipt, Journal, or Contra |
| **Financial Year (FY)** | April 1 - March 31. Books are isolated per FY with explicit open/close |
| **Opening Balance** | The balance of an account at the start of a financial year |
| **Narration** | A required free-text description on every transaction (except Contra) |
| **Transaction Audit Log** | The original state of a transaction before any edit; preserved immutably when a posted transaction is modified |
| **Transaction Number** | A human-readable reference in the format `{TYPE}-{YYYY}-{SEQ}` (e.g. `PAY-2024-001`), sequential per transaction type per FY, resets each April 1 |
| **Depreciation Rate** | The WDV rate (per Income Tax Act) on a fixed asset account, used to calculate year-end depreciation (e.g. 40% for computers, 15% for furniture) |
| **Half-Year Rule** | IT Act rule: assets added after October 3 attract 50% of normal depreciation in the year of acquisition |
| **Accumulated Depreciation** | A contra-asset account paired with each fixed asset, holding the total depreciation posted to date |
| **Lot** | A single purchase of an investment: date, units (milliunits), cost per unit (paise), remaining units - used for FIFO capital gains calculation |
| **Holding** | The set of open lots for a given investment account |
| **STCG** | Short-Term Capital Gain - equity held < 12 months, taxed at 20% |
| **LTCG** | Long-Term Capital Gain - equity held ≥ 12 months, taxed at 12.5% above ₹1.25L exemption |
| **Staging Area** | A temporary holding space for AI-parsed bank statement rows, pending user review and confirmation before being posted as transactions |
| **Price Quote** | A fetched market price for an investment account on a given date - NAV for equity MFs (from AMFI), price for stocks (from NSE/yfinance); used to calculate current value and unrealized gain on the Portfolio screen |
| **Price Source ID** | The identifier used to fetch prices for an investment account - AMFI scheme code for equity MFs, NSE ticker symbol (e.g. `INFY`, `HDFCBANK`) for stocks |
| **Transaction Date** | The date the transaction actually occurred - canonical for all reports |
| **Entry Date** | The date the transaction was recorded in Stow - stored as metadata, never used in reports |
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
│   └── Reserves & Surplus (Retained Earnings opening balance updated at new FY creation - see ADR 005)
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
├── Investments                 ← FD, equity MF, stock accounts live here
└── Current Assets
    ├── Bank Accounts
    ├── Cash-in-Hand
    └── Sundry Debtors

Profit & Loss
├── Income
│   ├── Direct Income           ← Salary, freelance income
│   └── Indirect Income         ← Interest income (FD, savings), capital gains income
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
| **Journal** | General adjusting entry - also used for all investment movements (buy, sell, FD open/mature) |
| **Contra** | Transfer between two cash/bank accounts |

### Financial Year Lifecycle
1. **Open** - FY is created, opening balances entered
2. **Active** - transactions can be posted
3. **Locked** - FY is closed, no further edits; net profit calculated and stored on the FY record. Retained Earnings is updated via opening balance carry-forward when the next FY is created (see ADR 005)

FY POST validates that the date range does not overlap any existing financial year.

### Opening Balances
- Dedicated bulk-entry screen when a new FY is created
- Each account's opening balance is also editable individually until its first transaction is posted

### Investments
Investment accounts are split into four sub-types with different tracking needs:

| Sub-type | Capital Gains | Model |
|---|---|---|
| Equity Mutual Funds | Yes - STCG/LTCG | FIFO lots (milliunits, cost_per_unit in paise) |
| Direct Stocks | Yes - STCG/LTCG | FIFO lots (milliunits, cost_per_unit in paise) |
| Fixed Deposits | No - interest is income | FdMetadata: principal (paise), rate (bps), maturity date, compounding |
| Real Estate | v2 | - |

#### Unit / amount conventions
- Lot units stored as **milliunits**: 1 unit = 1,000 milliunits (e.g. 12.345 units → 12345)
- `cost_per_unit` = NAV/price in **paise per unit** (not per milliunit): `NAV_rupees × 100`
- Total cost formula: `units_milliunits × cost_per_unit // 1000` → paise
- All money amounts throughout the system are in **paise** (₹1 = 100 paise)

#### Investment double-entry
Every investment operation creates a balanced Journal transaction automatically:

| Operation | Debit | Credit |
|---|---|---|
| Open FD | FD account (+principal) | Bank account (-principal) |
| Mature FD | Bank account (+principal+interest) | FD account (-principal), Interest Income (-interest) |
| Buy MF/stock | Investment account (+total_cost) | Bank/trading account (-total_cost) |
| Sell MF/stock | Bank/trading account (+proceeds) | Investment account (-cost_basis), STCG/LTCG account (-gain) or Capital Loss (+loss) |

When an investment-opening transaction is deleted, the cascade also removes:
- FD: deletes FdMetadata, archives the FD account
- MF/stock buy: deletes associated Lot records and any CapitalGainEntry records

#### Capital Gains
- On sale, FIFO lots are consumed and STCG/LTCG calculated automatically
- STCG/LTCG tax rates managed via a versioned `CapitalGainsTaxRule` table (not hardcoded)
- Capital Gains Report generated for ITR Schedule CG

### Live Prices (Equity MF & Stocks)
- Each equity MF account carries an AMFI scheme code (**Price Source ID**); each stock account carries an NSE ticker symbol
- A daily background job fetches current NAV from AMFI/mfapi.in and stock prices from NSE bhavcopy or yfinance
- Fetched prices stored in `price_quote` table (account, price, date)
- **Current value** = latest price quote × open units; **Unrealized gain** = current value - cost basis
- Portfolio screen shows current value and unrealized gain only when a price quote exists; otherwise shows cost basis only

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
| Profit & Loss | Income - Expenses for a date range |
| Cash Flow Statement | Indirect method; accounts tagged Operating/Investing/Financing |
| Capital Gains Report | FIFO-based STCG/LTCG breakdown for equity MFs and stocks; for ITR Schedule CG |

### Cash Flow Tagging
- Seed data sets defaults (Bank Accounts → Operating, Fixed Assets → Investing, Loans → Financing)
- Accounts flagged as "investment accounts" at creation are tagged Investing
- Tags are overridable per account

## AI Features

### Conversational Agent Architecture
All user-facing AI interactions flow through a **multi-agent system** built with `pydantic_ai` and the `subagents_pydantic_ai` library:

- **Orchestrator** (`backend/src/agent/orchestrator.py`) - the top-level pydantic_ai agent. Receives all user messages (text, images, PDF references), classifies intent, and delegates to specialised subagents via `SubAgentCapability`.
- **Subagents** (`backend/src/agent/subagents/`) - each is a focused pydantic_ai agent with its own tool set:

| Subagent | Responsibility |
|---|---|
| `transaction` | NL → parse → proposal → create / query / edit / delete transactions |
| `account` | Create / query / archive accounts |
| `import_agent` | Bank statement staging row review and bulk confirmation |
| `investment` | FD open/mature, equity MF/stock buy/sell, portfolio queries |
| `recurring` | Create / confirm / skip recurring schedules |
| `report` | P&L, balance sheet, cash flow, capital gains queries |

### Progress Events
`backend/src/agent/activity.py` provides a ContextVar-based activity bus:
- `emit(label: str)` puts a short label on a per-request `asyncio.Queue`
- WebSocket transport drains the queue in parallel with the agent run, sending `{"type": "progress", "label": "..."}` JSON frames to the frontend
- Frontend (ChatSidebar) shows the label next to the typing dots indicator
- Telegram transport shows `send_chat_action("typing")` every 4 seconds while the agent runs

### Transport Layers
- **WebSocket** (`backend/src/agent/transport/websocket.py`) - web chat. Creates a progress queue, sets the ContextVar, drains progress messages while the agent runs, then sends the final response. Handles text, images (`BinaryContent`), and PDF uploads. PDFs are pre-uploaded to `POST /imports`; orchestrator receives `[IMPORT_BATCH:{id}:{filename}]`.
- **Telegram** (`backend/src/agent/transport/telegram/`) - same orchestrator, separate entry point. Handles photo messages as `BinaryContent` for vision, PDF documents as import batches. Converts LLM markdown output to Telegram-compatible HTML via `_md_to_html()`.

### Natural Language Transaction Entry
1. User types a loose narrative: "paid electricity bill 2400 from HDFC last Tuesday"
2. Orchestrator delegates to `transaction_agent`
3. `transaction_agent` calls `parse_natural_language` → returns a proposal JSON (never auto-posts)
4. Orchestrator emits a `PROPOSAL:` line + renders a human-readable card for the user
5. On "confirm": orchestrator delegates `"confirm: <JSON>"` back to `transaction_agent` → `create_transaction`
6. On "decline": friendly cancellation; on edit request: update fields and re-show card

`transaction_agent` explicitly refuses investment buy/sell/FD requests - those must go to `investment_agent`.

### Investment Operations (via agent)
The orchestrator routes any mention of "buy", "mutual fund", "FD", "stock", "NAV", "units", "SIP", etc. directly to `investment_agent` (never to `transaction_agent`).

`investment_agent` directly calls backend endpoints - no proposal card step:
- `create_fd` → `POST /investments/fds` - creates account + FdMetadata + balanced journal
- `mature_fd` → `POST /investments/fds/{id}/mature`
- `buy_investment` → `POST /investments/{id}/buy`
- `sell_investment` → `POST /investments/{id}/sell`

Parameter convention in agent tools:
- `account_id` = the INVESTMENT account (debited on buy)
- `bank_account_id` = the PAYING account (credited on buy; debited on sell to receive proceeds)

### UPI Screenshot (Vision)
- User sends a UPI payment screenshot via web chat or Telegram
- Orchestrator passes `BinaryContent` to the LLM vision model (text prompt must come first in the list)
- LLM extracts: merchant name, amount, reference number
- `_get_merchant_rules` tool called to pre-fill payee account from saved merchant rules
- Proposal card shown; user confirms to post

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

### Markdown Rendering
- Chat UI: agent responses rendered via `react-markdown` + `remark-gfm` with full component overrides (no prose classes); user messages stay `whitespace-pre-wrap`
- Telegram: `_md_to_html()` converts LLM markdown → Telegram HTML using the `markdown` package + regex cleanup for unsupported tags

### Background Scheduler
- APScheduler 4.x running in the FastAPI process, timezone: Asia/Kolkata (IST)
- Jobs: daily price fetch (equity MF NAV + stock prices) and recurring transaction queue population
- Management API at `/scheduler/jobs` - list jobs, trigger manually

### AI Stack
- Any OpenAI-compatible local inference server (oMLX, Ollama, LM Studio, vLLM, etc.)
- LLM client: `pydantic_ai.Agent` wrapping the OpenAI-compatible inference server
- LLM config stored in DB and editable at runtime via Settings → AI / LLM (no restart required)
- `normalize_base_url()` in `backend/src/stow/ai_config.py` rewrites `localhost` → `host.docker.internal` for Docker
- Configured via `STOW_LLM_BASE_URL` and `STOW_LLM_MODEL` environment variables (overridden by DB config if set)
- No external API calls - all inference is on-device

## Telegram Bot

The Telegram bot provides natural-language accounting via the same backend. It complements the web app - quick interactions via bot, deep work via web.

### Design Decisions

| Decision | Choice |
|---|---|
| Scope | Complements web app - no need to replicate full web UX in bot |
| User model | Single user, simple `telegram_user_id` → `user_id` mapping on `/start` |
| Setup | Simple `/start` mapping - no auth flow needed |
| Interaction | Free text for daily use, slash commands for specific workflows (`/balance`, `/recurring`, `/import`) |
| Parsing | Full orchestrator + subagent pipeline - same as web chat |
| Confirmation | Proposal card for regular transactions; investments execute directly |
| Conversation history | In-memory dict keyed by `telegram_user_id`; reset on `/start` |
| Screenshots | `BinaryContent` passed to LLM vision - text prompt first, then image bytes |
| Bank import | PDF uploaded to `/imports`, then `[IMPORT_BATCH:{id}:{filename}]` sent to orchestrator |
| Typing indicator | `send_chat_action("typing")` every 4 s while agent runs |
| Response format | Markdown → Telegram HTML via `_md_to_html()`; `parse_mode="HTML"` |
| Bot framework | `aiogram 3.x` - async-native, integrates with FastAPI ecosystem |
| AI infrastructure | Reuses existing `pydantic_ai` orchestrator - same LLM provider, same config |

### Bot Vocabulary

| Term | Meaning |
|---|---|
| **Proposal Card** | A scannable summary of the parsed transaction shown before posting - amount, type, accounts, date, narration |
| **Staging Row** | A parsed bank statement line awaiting confirmation - same as web app's staging area |
| **Daily Digest** | A single message listing all recurring transactions due today, with individual [Confirm] [Skip] buttons |

## File Structure

```
backend/src/
├── agent/
│   ├── agent.py                   # Unified pydantic_ai agent (~40 tools, one comprehensive prompt)
│   ├── deps.py                    # Shared dependency injection (HTTP client, base URL)
│   ├── activity.py                # ContextVar-based progress event bus (emit())
│   └── transport/
│       ├── websocket.py           # Web chat - progress drain, image/PDF pre-upload
│       ├── proposal.py            # Proposal card parser (shared across transports)
│       └── telegram/
│           ├── bot.py             # aiogram Bot instance + dispatcher setup
│           ├── handlers.py        # All Telegram event handlers; _md_to_html(); _keep_typing()
│           └── keyboard.py        # Inline keyboard builders (Confirm/Decline)
└── stow/
    ├── routers/                   # FastAPI route modules (one per domain)
    │   ├── transactions.py        # CRUD; cascades Lot/FdMetadata on delete
    │   ├── investments.py         # FD create/mature/list, buy, sell, holdings, portfolio
    │   ├── financial_years.py     # FY CRUD; overlap validation on create
    │   └── ...
    ├── models.py                  # SQLModel ORM models
    ├── ai_config.py               # LLM config load/save + normalize_base_url()
    ├── import_pipeline.py         # PDF parsing → staging rows
    ├── import_parsers.py          # Per-bank PDF parsers
    ├── recurring.py               # Queue generation logic
    ├── scheduler.py               # APScheduler job definitions
    ├── reports/                   # Report generation + PDF export
    └── investments/
        ├── schemas.py             # Pydantic models for buy/sell/FD/lot/portfolio
        ├── repository.py          # LotRepository: buy(), sell(), holdings(), capital_gains()
        ├── fd.py                  # accrued_interest() helper
        └── prices.py              # PriceRepository: latest(), store()
```

## Technology Stack

| Layer | Choice |
|---|---|
| Frontend | Vite + React 19 + TanStack Query v5 + react-markdown + remark-gfm + lucide-react (no component library - custom design system) |
| Styling | Tailwind CSS v4 (`@import "tailwindcss"` syntax) |
| Backend | FastAPI (Python) |
| ORM | SQLModel + Alembic |
| Database | PostgreSQL |
| AI | pydantic_ai + OpenAI-compatible local inference (oMLX, Ollama, LM Studio, vLLM) |
| Scheduler | APScheduler 4.x (IST timezone) |
| PDF export | WeasyPrint or ReportLab |
| PDF parsing | pdfplumber or pymupdf |
| Telegram | markdown (Python package, for HTML conversion) + aiogram 3.x |
| Deployment | Docker Compose (local machine) |

## Project Structure

```
stow/
├── frontend/          # Vite + React SPA
│   └── src/
│       ├── pages/     # Dashboard, Transactions, Accounts, Reports, Portfolio, Settings, Onboarding
│       └── components/# Sidebar, ChatSidebar, TransactionEntrySheet, ProposalCard, AccountSheet, ...
├── backend/           # FastAPI application
│   └── src/
│       ├── agent/     # Unified agent + transport layers (WebSocket, Telegram)
│       └── stow/      # FastAPI app, routers, models, reports, investments, scheduler
├── docs/
│   └── adr/           # Architecture Decision Records
├── e2e/               # Playwright end-to-end tests
├── QA_CHECKLIST.md    # Comprehensive manual QA checklist (all user-facing features)
├── docker-compose.yml
└── CONTEXT.md
```

## Key Constraints

- **Single user** - no multi-tenancy, no user table, minimal auth
- **Local only** - runs on developer's machine via Docker Compose
- **INR only** - currency field stubbed for future multi-currency support
- **No invoicing** - bookkeeping only, no GST return generation
- **Indian FY** - April 1 to March 31, hard year boundaries
- **Attachments** - stored on local Docker volume, path saved in DB
