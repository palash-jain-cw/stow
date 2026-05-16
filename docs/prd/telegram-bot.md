## Problem Statement

Data entry in Stow today requires navigating multiple web UI screens. The user wants to operate the entire app conversationally — typing naturally, forwarding screenshots, uploading PDFs — from both a phone (Telegram) and the web browser. The existing bank import UI and NL transaction entry widget are being replaced by this agent interface.

## Solution

A central pydantic_ai agent with tools, subagents, and skills that can operate the full Stow backend. The agent is exposed through two transport layers:

1. **Telegram bot** — mobile-first, always available, handles text + images + PDFs
2. **Web chat window** — persistent chat panel in the web app, same agent, same capabilities

The web app itself becomes a read-heavy companion: ledger views, reports, portfolio, settings. All data entry and operations move to the agent.

### What Gets Removed

- Bank import web UI page — replaced by agent's `bank_reconciler` skill
- NL transaction entry widget — replaced by agent's `transaction_entry` skill
- `POST /ai/process-image` REST endpoint — vision is a model capability used agent-internally, not an exposed API

### Web UI Changes (Non-Agent)

**Accounts sidebar:**
- Default: show only bank accounts and cash accounts
- Everything else (expenses, income, equity, investments, etc.) collapsed under a "See more" toggle
- Clicking an account loads the full ledger for that account in the main body (all transactions, not a summary card)

**Keyboard-driven navigation:**
- All data entry forms (opening balances, FY creation, settings) must be fully operable by keyboard
- Tab moves between fields; account fields support type-to-filter + arrow keys + Enter to select
- No mouse required for any data entry path

**Transaction validation:**
- From account and To account are mandatory on every transaction
- Narration is optional

## User Stories

### Agent — Transaction Entry

1. As a Stow user, I want to type "paid electricity bill 2400 from HDFC last Tuesday" and have the agent parse it into a structured proposal so that I can record transactions without opening any form
2. As a Stow user, I want the agent to always show a confirmation card with [Confirm] [Edit] [Decline] before posting so that I never accidentally post incorrect entries
3. As a Stow user, I want to tap any field in the proposal card (account, date, amount, narration) to edit it inline so that I can correct mistakes without re-typing the whole entry
4. As a Stow user, I want the agent to pre-fill the most likely accounts based on historical patterns for the same counterparty so that I spend less time selecting accounts
5. As a Stow user, I want the agent to show top 3-5 account suggestions when the pre-fill is ambiguous so that I can quickly pick the right one
6. As a Stow user, I want the agent to support all voucher types (Payment, Receipt, Journal, Contra) through natural language so that I can record any transaction type
7. As a Stow user, I want the agent to handle amounts in both paise and rupees so that "500" and "₹500" both work
8. As a Stow user, I want the agent to parse relative dates ("last Tuesday", "yesterday") correctly so that I don't have to think about the calendar
9. As a Stow user, I want the agent to show a concise confirmation after posting so that I know it was successful

### Agent — Image & Screenshot Parsing

10. As a Stow user, I want to forward a UPI payment screenshot to the agent so that it extracts amount, date, UPI ID, and merchant and proposes a transaction
11. As a Stow user, I want the agent to match the extracted UPI ID against merchant rules so that the account is pre-filled without me having to look it up
12. As a Stow user, I want the agent to handle images forwarded from WhatsApp, the phone gallery, or the web chat so that the source doesn't matter

### Agent — Bank Import

13. As a Stow user, I want to send a bank statement PDF to the agent and have it parse, stage, and walk me through confirmation conversationally so that I don't need to open the import UI
14. As a Stow user, I want the agent to auto-confirm non-duplicate rows and surface only flagged duplicates for my review so that I spend minimal time on imports
15. As a Stow user, I want to confirm, skip, or edit each flagged row via inline buttons so that the review is fast

### Agent — Queries & Reports

16. As a Stow user, I want to ask "what's my HDFC balance" or "how much did I spend on food this month" and get an instant answer so that I don't have to navigate to the reports screen
17. As a Stow user, I want follow-up [Breakdown] and [Report] buttons on query responses so that I can drill into details when needed
18. As a Stow user, I want to ask "how's my portfolio doing" and get a summary of holdings and unrealized gains so that I have a quick pulse check

### Agent — Recurring Transactions

19. As a Stow user, I want to type `/recurring` and get a digest of all recurring transactions due today so that I can process them in one go
20. As a Stow user, I want each recurring item to have [Confirm] [Skip] [Edit] buttons so that processing takes seconds

### Agent — General

21. As a Stow user, I want the agent to check the active financial year before posting so that transactions are always assigned to the correct FY
22. As a Stow user, I want the agent to learn my account selection patterns over time so that suggestions improve the more I use it
23. As a Stow user, I want the agent to handle errors gracefully with retry logic and friendly messages so that I'm never left confused by failures
24. As a Stow user, I want the agent to be identical whether I access it from Telegram or the web chat window so that I don't have to learn two interfaces
25. As a Stow user, I want to type `/start` in Telegram and have the bot link my Telegram ID automatically so that there is no separate auth flow

### Web UI

26. As a Stow user, I want the accounts sidebar to show only bank accounts and cash by default so that it's not overwhelming
27. As a Stow user, I want a "See more" toggle to reveal the full account tree so that I can access any account when I need it
28. As a Stow user, I want clicking an account to show the full ledger for that account in the main body so that I can review all transactions without navigating away
29. As a Stow user, I want all data entry forms to be fully keyboard-navigable so that I never have to reach for the mouse

## Implementation Decisions

### Agent Architecture

The agent is implemented with **tools** (thin wrappers over backend endpoints) and **skills** (high-level capabilities with domain logic and conversation flows).

#### Tools

| Tool | Endpoint | Purpose |
|------|----------|---------|
| `create_transaction` | `POST /transactions` | Post a double-entry transaction |
| `list_transactions` | `GET /transactions` | Query/filter transactions |
| `get_transaction` | `GET /transactions/{id}` | Fetch single transaction |
| `update_transaction` | `PUT /transactions/{id}` | Edit narration/date/tags |
| `delete_transaction` | `DELETE /transactions/{id}` | Remove a transaction |
| `parse_natural_language` | `POST /ai/parse-transaction` | Text → structured proposal |
| `list_accounts` | `GET /accounts` | All accounts with balances |
| `get_account` | `GET /accounts/{id}` | Single account + ledger |
| `create_account` | `POST /accounts` | Add a new ledger |
| `archive_account` | `POST /accounts/{id}/archive` | Soft-delete an account |
| `list_reports` | `all /reports/*` | Trial balance, P&L, balance sheet, cash flow |
| `get_financial_years` | `GET /financial-years` | Current/active FY info |
| `create_fd` | `POST /investments/fds` | Create fixed deposit |
| `buy_investment` | `POST /investments/{id}/buy` | Purchase MF/stock lot |
| `sell_investment` | `POST /investments/{id}/sell` | Sell lots (FIFO) |
| `get_holdings` | `GET /investments/{id}/holdings` | Current portfolio lots |
| `get_portfolio` | `GET /investments/{id}/portfolio` | Current value + unrealized gains |
| `get_capital_gains` | `GET /investments/{id}/capital-gains` | STCG/LTCG summary |
| `list_fds` | `GET /investments/fds` | All FDs with accrued interest |
| `import_statement` | `POST /imports` | Upload PDF → staging |
| `review_staging` | `GET /imports/{batch}/rows` | Review parsed rows |
| `confirm_staging` | `POST /imports/{batch}/confirm` | Post all confirmed rows |
| `match_staging_row` | `POST /imports/{batch}/rows/{id}/match` | Match to existing txn |
| `update_staging_row` | `PUT /imports/{batch}/rows/{id}` | Edit account/tags |
| `get_recurring_due` | `GET /recurring/due-today` | Today's pending recurring |
| `confirm_recurring` | `POST /recurring/queue/{id}/confirm` | Post a recurring |
| `skip_recurring` | `POST /recurring/queue/{id}/skip` | Skip a recurring |

#### Skills

1. **transaction_entry** — Parses free text via `parse_natural_language`, presents a proposal card, handles field-level edits, posts via `create_transaction` on confirm. Enforces: both accounts required, narration optional, active FY check, double-entry rules.

2. **screenshot_parser** — Receives image (forwarded UPI screenshot), passes to vision-capable model alongside account list and merchant rules, extracts amount/date/UPI ID/merchant, maps to account, hands off to `transaction_entry` for confirmation. No separate REST endpoint — vision runs inside the agent.

3. **financial_query** — Answers balance and spending questions by composing `list_transactions`, `list_accounts`, and `list_reports` calls, then summarises in plain language with optional drill-down buttons.

4. **report_generator** — Generates and delivers structured reports. Fetches from `/reports/*`, formats as readable summary, offers further breakdown.

5. **investment_tracker** — Handles investment operations end-to-end: buy/sell lots, check portfolio value, review capital gains. Domain knowledge: FIFO, milliunits, paise, STCG/LTCG rules, FD compounding.

6. **bank_reconciler** — Full PDF import flow: `import_statement` → `review_staging` → conversational row-by-row review (auto-confirm non-duplicates, surface flagged rows) → `confirm_staging`. Replaces the web import UI entirely.

7. **recurring_manager** — Proactive recurring handling triggered by scheduler. Fetches due items, DMs user, handles confirm/skip/edit per item via inline buttons.

### Transport Layers

#### Telegram

- `aiogram 3.x` — async-native, compatible with FastAPI lifespan
- Long-polling only (no webhook mode)
- Runs inside the existing FastAPI process via lifespan event
- Handles text messages, forwarded images, forwarded PDFs
- `/start` auto-links `telegram_user_id` to Stow user (single-user, no auth flow)
- Slash commands: `/help`, `/balance`, `/recurring`, `/import`

#### Web Chat Window

- Persistent chat panel in the web app (sidebar or floating drawer)
- Connects to the same agent via a new WebSocket or SSE endpoint
- Supports text input and file upload (images, PDFs)
- Renders proposal cards as interactive UI components (buttons → inline edit forms)
- Shares session with the web app — no separate auth

### Module Structure

New `telegram_bot/` package alongside the existing `stow/` package:

- **bot.py** — aiogram bot setup + FastAPI lifespan integration
- **router.py** — intent classification (entry / query / import / recurring / image / other)
- **state.py** — in-memory state machine per user, 10-minute TTL
- **handlers/**
  - `start.py` — `/start`, user linking
  - `text.py` — free text → skill dispatch
  - `image.py` — image download → `screenshot_parser` skill
  - `document.py` — PDF download → `bank_reconciler` skill
  - `edit.py` — inline keyboard callbacks for field edits
  - `recurring.py` — `/recurring` digest
- **proposals.py** — card text + inline keyboard builder
- **keyboard.py** — inline keyboard layouts
- **queries.py** — query helpers wrapping backend endpoints
- **utils.py** — date resolution, amount parsing, error formatting

New WebSocket/SSE router in `stow/routers/chat.py` for the web chat window.

### Schema Changes

New `TelegramUser` table in `models.py`:

- `id` — auto-increment primary key
- `telegram_user_id` — BIGINT, UNIQUE, not null
- `username` — optional string

No `user_id` FK — single-user app, mapping is implicit.

### State Machine

`idle` → `parsing` → `reviewing` → `editing` → `confirming` → `posted`

In-memory dict keyed by `telegram_user_id` (Telegram) or session ID (web chat). 10-minute TTL. State lost on restart — acceptable for a single-user local app.

### Conversation Flows

**Quick entry:**
```
You: paid ₹850 for zomato
Bot: 📝 Payment #PAY-2026-042
     ₹850  HDFC Bank → Food & Dining
     Date: 16 May 2026  Narration: Zomato
     [Confirm] [Edit] [Decline]
```

**UPI screenshot:**
```
You: [forwards screenshot]
Bot: 📸 ₹2,400 to BESCOM on 14 May
     HDFC Bank → Electricity Expense
     [Confirm] [Change Account] [Decline]
```

**Bank import:**
```
You: [forwards HDFC May statement PDF]
Bot: Parsed 47 rows. Auto-confirming 44 (no duplicates).
     3 rows need review:
     1/3 — ₹5,000 on 3 May (possible duplicate of PAY-2026-031)
     [Confirm anyway] [Skip] [View existing]
```

**Financial query:**
```
You: how much did I spend on rent this year?
Bot: ₹2,16,000 — 12 payments of ₹18,000
     [Monthly breakdown] [Full report]
```

**Portfolio check:**
```
You: how's my portfolio?
Bot: 📊 HDFC Equity MF  ₹50,000 → ₹62,400 (+24.8%)
     Unrealized gain: ₹12,400
     [Full holdings] [Capital gains]
```

## Testing Decisions

Tests focus on behavior and state transitions. Mock the LLM, Telegram API, and database.

1. **State machine** (`state.py`) — transitions, TTL expiry, concurrent edit handling
2. **Proposal builder** (`proposals.py`) — card text and keyboard construction across field types
3. **Intent router** (`router.py`) — correct dispatch for text / image / PDF / slash commands
4. **Query helpers** (`queries.py`) — balance, spending, history with mocked DB
5. **End-to-end flows** — text → parse → propose → edit → confirm → post; image → parse → propose → confirm; PDF → stage → review → confirm

Existing `tests/` uses `pytest` + `pytest-asyncio`. New tests follow the same patterns.

## Out of Scope

- Multi-user support
- Webhook mode
- Message queuing
- Voice message support
- Full reporting via bot (web app handles deep reporting)
- Bot configuration UI (configured via web app settings)
- Multiple bot instances

## Further Notes

- The agent is the primary interface for data entry; the web UI is the primary interface for reading and analysis
- Bank import web UI and NL transaction entry widget are removed — the agent fully replaces them
- Vision (image → transaction) is a model capability used inside the agent; no new REST endpoint is added
- `aiogram` adds ~500KB to the Docker image — negligible
- ADR 024 (`docs/adr/024-telegram-bot.md`) documents design rationale and needs to be updated to reflect this architecture
