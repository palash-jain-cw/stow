# ADR 024 — Telegram Bot for Natural-Language Accounting

**Status:** Accepted
**Date:** 2026-05-16

---

## Context

The user wants to interact with Stow's accounting capabilities via Telegram bot in addition to the web app. This provides a fast, natural-language interface for daily micro-interactions (posting transactions, querying balances, importing bank statements) while deep work (reporting, investments, bulk operations) continues on the web app.

---

## Decisions

### 1. Scope — Complement, Not Replace

The Telegram bot complements the existing web app. It does not replicate the full web UX. The bot handles:

- Natural language transaction entry (text + screenshots)
- Quick queries (balances, recent transactions, totals)
- Bank statement import (`/import`)
- Recurring transaction management (`/recurring`)

The web app remains the primary interface for deep workflows.

### 2. User Model — Single User Mapping

The user is a single user. The bot maps `telegram_user_id` → `user_id` via a simple `telegram_user_id` foreign key on the existing `User` table (or a new `TelegramUser` mapping table). No authentication flow is needed — `/start` creates or retrieves the mapping.

```sql
CREATE TABLE telegram_user (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_user_id BIGINT UNIQUE NOT NULL,
    user_id INTEGER NOT NULL REFERENCES user(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 3. Interaction — Hybrid: Free Text + Slash Commands

- **Free text** is the default for daily use. The user types naturally: "paid electricity bill 2400 from HDFC last Tuesday"
- **Slash commands** handle specific workflows: `/import` (bank statement), `/recurring` (recurring management)

### 4. Parsing — Centralized LLM Call

A single LLM call extracts all transaction fields from the user's message:

- `type` (payment/receipt/journal/contra)
- `date` (resolved against current date)
- `amount` (in paise)
- `from_account_id` / `to_account_id` (resolved against account list)
- `narration` (free text)

The LLM call receives: current date, list of active accounts (id, name, group_id), and 10 most recent transactions as context — same as the existing `/ai/parse-transaction` endpoint.

### 5. Confirmation — Always Confirm

The bot never auto-posts a transaction. Every parsed transaction is shown as a **proposal card** with inline keyboard options:

```
Amount: ₹2,400
Type: Payment
From: HDFC Bank
To: Electricity Expense
Date: 2026-05-15
Narration: Electricity bill payment

[Confirm] [Edit] [Decline]
```

### 6. Editing — Inline Keyboard Field Buttons

When the user taps [Edit], each field becomes a tapable button:

```
Edit which field?

[HDFC Bank] [Electricity Expense] [2026-05-15] [₹2,400] [Narration]
[← Back]
```

Tapping a field shows a list of options (e.g., account list) or a text input for free-form values.

### 7. Account Selection — Learning + Suggestions

The bot learns from past transactions which accounts are typically used as the "to" account for each counterparty/merchant. When parsing, it:

1. Pre-fills the most likely account based on historical pairings
2. Shows top 3-5 alternative accounts for override
3. Stores new pairings when the user chooses a different account

### 8. Query Responses — One-Line + Expand

For queries ("balance in HDFC", "how much did I spend on electricity?"):

- Default: one-line answer ("HDFC: ₹45,230" or "Electricity: ₹12,400 this month")
- Inline keyboard: [breakdown] [report] for detail
- Breakdown: short list of transactions
- Report: full formatted report

### 9. Screenshot Processing — Vision LLM

When the user forwards a UPI screenshot, the bot:

1. Extracts the image (Telegram file URL or download)
2. Sends to new `POST /ai/process-image` endpoint (vision-capable LLM)
3. Extracts: amount, date, beneficiary/upi_id, transaction status
4. Creates a payment proposal (type is inferred from beneficiary name — if it's a UPI ID, it's a payment; if it's a refund, it's a receipt)
5. Shows proposal card as usual

The image endpoint follows the same pattern as `/ai/parse-transaction` — passes account list and recent transactions as context.

### 10. Bank Import — Auto-Confirm Non-Duplicates

The `/import` workflow:

1. User sends a PDF/CSV via bot
2. Backend parses the file (existing import pipeline)
3. Staging rows are created with duplicate detection
4. The bot sends a single message with all rows:
   - Confirmed rows (non-duplicates): green checkmark + account assignment
   - Duplicate rows: flagged with [Review] button
5. Non-duplicate rows are auto-confirmed and posted
6. Duplicate rows are presented for manual review

### 11. Recurring — Daily Digest

The bot sends a daily digest message at a fixed time (e.g., 08:00 IST) listing all recurring transactions due today:

```
Today's recurring transactions:

1. Netflix — ₹649
   From: HDFC Bank
   [Confirm] [Skip] [Edit]

2. SIP — ₹5,000
   From: HDFC Bank
   To: Axis Bluechip Fund
   [Confirm] [Skip] [Edit]
```

Each item has individual [Confirm] [Skip] [Edit] buttons. The bot updates the message inline as the user responds.

### 12. Architecture — Same FastAPI Process

The Telegram bot runs in the same FastAPI process as the web backend:

- Same `main.py`, same router registration
- Same DB session (via `get_session` dependency)
- Same APScheduler instance (`app.state.scheduler`) — no additional infrastructure
- Same AI agent (pydantic_ai) — same config, same LLM

The bot starts via a FastAPI lifespan event:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # ... existing scheduler setup ...

    # Start Telegram bot long-polling
    bot_task = asyncio.create_task(start_bot_polling())
    yield
    bot_task.cancel()
```

### 13. State Management — In-Memory with TTL

Multi-step state (editing a proposal) is stored in an in-memory dict keyed by `telegram_user_id`:

```python
bot_state = {}  # telegram_user_id → BotState

class BotState:
    mode: Literal["idle", "parsing", "reviewing", "editing", "confirming", "posted"]
    parsed_data: dict  # Transaction fields being edited
    ttl: datetime  # Expires after 10 minutes
```

TTL: 10 minutes of inactivity. On timeout or restart, state is lost — the user simply re-sends the message. This is acceptable for a single-user local app.

### 14. Error Handling — Retry + User-Friendly Messages

- **Transient errors** (503, timeout): Retry 3 times with exponential backoff
- **LLM errors** (parsing fails): Show "I couldn't understand that — try rephrasing" with a hint
- **Backend unavailable**: Show "Backend unavailable, try again in a moment"

No message queuing — the user is the only user, they can re-send.

### 15. Financial Year — Always Check Active FY

The bot always checks the active FY from the backend (`GET /financial-years`) before creating any transaction. If no FY is open, it asks the user to open one first. No stale state — the bot always reads from the single source of truth.

### 16. Bot Framework — aiogram 3.x

`aiogram 3.x` is used for the Telegram bot:

- Async-native — integrates cleanly with FastAPI's async ecosystem
- Long-polling for message handling
- Excellent type hints and documentation
- Active maintenance

### 17. Bot File Structure

```
backend/src/stow/telegram_bot/
├── __init__.py          # Bot initialization, dispatcher
├── bot.py               # aiogram Bot instance, long-polling setup
├── router.py            # Intent classification (entry/query/import/investment/other)
├── state.py             # In-memory state machine (BotState class, TTL)
├── handlers/
│   ├── start.py         # /start handler
│   ├── text.py          # Free text handler
│   ├── image.py         # Image handler
│   ├── edit.py          # Inline keyboard edit handler
│   ├── import_handler.py # /import handler
│   ├── recurring.py     # /recurring handler
│   └── query.py         # Query handler
├── proposals.py         # Proposal card builder
├── keyboards.py         # Inline keyboard builders
├── queries.py           # Backend query helpers
└── utils.py             # Shared utilities
```

---

## Consequences

- The bot adds minimal complexity — it's a thin layer over existing API endpoints
- The in-memory state is lost on restart, but this is acceptable for a single-user local app
- The bot shares the same AI infrastructure as the web app — same LLM, same config, same cost
- The bot extends the user interface surface but doesn't change the core data model
- The bot can be started/stopped independently of the web app (same process, same port)
- The `aiogram` dependency adds ~500KB to the Docker image, which is negligible
