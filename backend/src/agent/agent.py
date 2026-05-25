from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Optional

from pydantic_ai import Agent, RunContext

from agent.activity import emit
from agent.deps import StowDeps
from agent.transport.proposal import execute_proposal, format_post_success
from agent.upi_matching import resolve_upi_accounts
from agent.tool_errors import is_tool_error, stow_delete, stow_get, stow_post, stow_put, tool_safe
from stow.import_pipeline import match_bank_account
from stow.ai_config import build_model

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are Stow, a conversational personal finance assistant for Indian users.
You help record transactions, import bank statements, answer financial queries,
and manage investments — entirely through conversation.

## Core Domain Knowledge

### Amounts
- All amounts are in **paise** (1 INR = 100 paise). "₹500" = 50000 paise.
- Display amounts to users as ₹X,XX,XXX (Indian comma format).

### Double Entry
- Every transaction has entries that sum to zero (debits = credits).
- **Payment**: money leaving a bank/cash account (from=bank, to=expense).
- **Receipt**: money entering a bank/cash account (from=income, to=bank).
- **Journal**: general adjusting entry; used for investments, depreciation, adjustments.
- **Contra**: transfer between two cash/bank accounts (no narration needed).
- `from_account` is CREDITED (money leaves), `to_account` is DEBITED (money arrives).

### Transaction Types — When to Use
- Use **payment** for: bills, purchases, rent, groceries, transfers to expense accounts.
- Use **receipt** for: salary credited, freelance income, refunds received.
- Use **journal** for: investment operations (buy/sell), depreciation, adjustments.
- Use **contra** for: cash deposit into bank, bank transfer between own accounts.

### Financial Years
- Indian FY: April 1 – March 31.
- Always resolve the FY for a transaction date using `get_fy_for_date`.
- Locked FYs cannot be edited. Open FYs can have transactions posted.

### Investments
- **NEVER** use create_transaction for investment buy/sell/FD operations.
  Use `buy_investment`, `sell_investment`, `create_fd`, `mature_fd` instead.
- Units stored as **milliunits** (1 unit = 1000 milliunits). Pass actual_units × 1000.
- `cost_per_unit` = NAV/price in **paise per unit** (NOT per milliunit): NAV_rupees × 100.
  Example: ₹810.45 → 81045.
- Total cost: units_milliunits × cost_per_unit / 1000 = total_cost_paise.
- Capital gains follow **FIFO** order — oldest lots sold first.
- **STCG** (equity): holding < 12 months, taxed at 20%.
- **LTCG** (equity): holding ≥ 12 months, taxed at 12.5% above ₹1.25L exemption.
- Interest rates are in **basis points** (750 bps = 7.50% p.a.).
- Portfolio shows current value and unrealized gain only when a price quote exists.

### Depreciation
- WDV method per Income Tax Act.
- Fixed assets carry a WDV rate (e.g., 40% for computers, 15% for furniture).
- **Half-year rule**: assets added after Oct 3 get 50% depreciation in year of acquisition.
- Depreciation is posted as a Journal entry (never auto-posted).

### GST & TDS
- GST accounts live under "Duties & Taxes": Input/Output CGST/SGST/IGST.
- TDS accounts: TDS Receivable, TDS Payable.

### Import Workflow
- Bank statement PDFs are uploaded to create a batch with staging rows.
- Review rows → auto-match with merchant rules → resolve unmapped rows → confirm.
- Rows without a suggested_account_id cannot post — ask the user.
- For duplicates: show ONE at a time with options: confirm anyway / skip / view existing.

### UPI Screenshots
- Extract: amount, merchant/payee, date, source bank, UPI ID/reference.
- Call `resolve_upi_accounts` with extracted details.
- If fully_resolved: delegate directly to create the transaction.
- If not fully resolved: ask ONE focused question for the missing side.

### Merchant Rules
- Pattern matching is case-insensitive substring with optional wildcard (*).
- Applied automatically during imports for faster matching.

### Recurring Transactions
- On the due date, items appear in the "Needs attention" queue.
- User can confirm as-is, edit then confirm, or skip.
- If no action by end of day, auto-posts as-is.

## Clarifying Questions
When information is missing or ambiguous, ask ONE focused question:
- Ambiguous account: "Which account did you pay from?"
- Missing date: "When did this happen?"
- Ambiguous amount: "Did you mean ₹500 or ₹5,000?"

Do NOT guess. Do NOT ask multiple questions at once.

## Error Recovery
When any tool returns a string starting with "Error:":
1. Read the error message carefully.
2. If it's a validation error (e.g., "account not found"), ask the user one question.
3. If it's a system error (e.g., "connection refused"), tell the user and suggest retrying.
4. Never give up after a single error — try once with corrected inputs.

## Tool Caching
When you call list_accounts, list_fds, or get_active_fy, remember the results
for the duration of the conversation. Do not call them again if you already have
the data. This saves time and reduces API calls.

## Formatting
- Amounts: ₹X,XX,XXX (Indian comma format)
- Dates: display as "DD Mon YYYY" (e.g., 16 May 2026)
- Keep responses short and actionable.
"""


# ─── Shared Tools ────────────────────────────────────────────────────────────

@tool_safe("get_current_datetime")
async def _get_current_datetime(ctx: RunContext[StowDeps]) -> dict | str:
    """Return the current date and time. Call this whenever you need to know today's date."""
    await emit("Checking date")
    now = datetime.now()
    return {
        "date": now.strftime("%Y-%m-%d"),
        "day": now.strftime("%A"),
        "display": now.strftime("%d %b %Y"),
        "time": now.strftime("%H:%M"),
    }


@tool_safe("get_active_fy")
async def _get_active_fy(ctx: RunContext[StowDeps]) -> dict | str:
    """Get the currently active financial year."""
    await emit("Looking up financial year")
    fys = await stow_get(ctx.deps, "/financial-years", tool_name="get_active_fy")
    if is_tool_error(fys):
        return fys
    assert isinstance(fys, list), f"Expected list of FYs, got {type(fys)}"
    active = next((fy for fy in fys if fy["status"] == "active"), None)
    if not active:
        active = next((fy for fy in fys if fy["status"] == "open"), None)
    return active or {}


@tool_safe("get_fy_for_date")
async def _get_fy_for_date(ctx: RunContext[StowDeps], date: str) -> dict | str:
    """Resolve the financial year for a transaction date (YYYY-MM-DD)."""
    await emit("Resolving financial year for date")
    return await stow_get(
        ctx.deps,
        "/financial-years/for-date",
        tool_name="get_fy_for_date",
        params={"date": date[:10]},
    )


@tool_safe("get_financial_years")
async def _get_financial_years(ctx: RunContext[StowDeps]) -> list[dict] | str:
    """List all financial years with start_date, end_date, and status."""
    await emit("Fetching financial years")
    return await stow_get(ctx.deps, "/financial-years", tool_name="get_financial_years")


# ─── Account Tools ───────────────────────────────────────────────────────────

@tool_safe("list_accounts")
async def _list_accounts(ctx: RunContext[StowDeps], include_archived: bool = False) -> list[dict] | str:
    """List all accounts with their current balances and group info.

    Args:
        include_archived: Whether to include archived accounts (default False)
    """
    await emit("Fetching accounts")
    return await stow_get(
        ctx.deps,
        "/accounts",
        tool_name="list_accounts",
        params={"include_archived": include_archived},
    )


@tool_safe("get_account")
async def _get_account(ctx: RunContext[StowDeps], account_id: int) -> dict | str:
    """Get a single account with its current balance.

    Args:
        account_id: Account ID
    """
    await emit("Fetching account")
    return await stow_get(ctx.deps, f"/accounts/{account_id}", tool_name="get_account")


@tool_safe("create_account")
async def _create_account(
    ctx: RunContext[StowDeps],
    name: str,
    group_id: int,
    investment_subtype: Optional[str] = None,
    currency: str = "INR",
) -> dict | str:
    """Create a new account in the ledger.

    Args:
        name: Account name
        group_id: Account group ID (determines nature: asset/liability/equity/income/expense)
        investment_subtype: equity_mf | stock | fd | ppf (for investment accounts)
        currency: Currency code, default INR
    """
    await emit("Creating account")
    body: dict[str, Any] = {"name": name, "group_id": group_id, "currency": currency}
    if investment_subtype:
        body["investment_subtype"] = investment_subtype
    return await stow_post(ctx.deps, "/accounts", tool_name="create_account", json=body)


@tool_safe("archive_account")
async def _archive_account(ctx: RunContext[StowDeps], account_id: int) -> dict | str:
    """Soft-delete (archive) an account. It will no longer appear in default listings.

    Args:
        account_id: Account ID to archive
    """
    await emit("Archiving account")
    return await stow_post(ctx.deps, f"/accounts/{account_id}/archive", tool_name="archive_account")


@tool_safe("get_account_ledger")
async def _get_account_ledger(ctx: RunContext[StowDeps], account_id: int) -> list[dict] | str:
    """Get the full transaction ledger for an account.

    Args:
        account_id: Account ID
    """
    await emit("Fetching account ledger")
    return await stow_get(ctx.deps, f"/accounts/{account_id}/ledger", tool_name="get_account_ledger")


@tool_safe("get_opening_balance")
async def _get_opening_balance(
    ctx: RunContext[StowDeps],
    account_id: int,
    fy_id: int,
) -> dict | str:
    """Get the opening balance for an account in a financial year.

    Args:
        account_id: Account ID
        fy_id: Financial year ID
    """
    await emit("Fetching opening balance")
    return await stow_get(
        ctx.deps,
        f"/accounts/{account_id}/opening-balance",
        tool_name="get_opening_balance",
        params={"fy_id": fy_id},
    )


@tool_safe("set_opening_balance")
async def _set_opening_balance(
    ctx: RunContext[StowDeps],
    account_id: int,
    fy_id: int,
    amount: int,
) -> dict | str:
    """Set the opening balance for an account in a financial year.

    The financial year must not be locked. Amount is in paise.

    Args:
        account_id: Account ID
        fy_id: Financial year ID
        amount: Opening balance in paise
    """
    await emit("Setting opening balance")
    return await stow_put(
        ctx.deps,
        f"/accounts/{account_id}/opening-balance",
        tool_name="set_opening_balance",
        json={"fy_id": fy_id, "amount": amount},
    )


# ─── Transaction Tools ───────────────────────────────────────────────────────

@tool_safe("parse_natural_language")
async def _parse_natural_language(ctx: RunContext[StowDeps], text: str) -> dict | str:
    """Parse a natural language transaction description into a structured proposal.

    Args:
        text: Natural language description, e.g. "paid electricity 2400 from HDFC last Tuesday"

    Returns:
        Structured transaction with type, date, amount (paise), narration, from_account_id,
        to_account_id, and optional tags.
    """
    await emit("Parsing transaction")
    return await stow_post(
        ctx.deps,
        "/ai/parse-transaction",
        tool_name="parse_natural_language",
        json={"text": text},
    )


@tool_safe("create_transaction")
async def _create_transaction(
    ctx: RunContext[StowDeps],
    type: str,
    date_str: str,
    narration: str,
    fy_id: int,
    from_account_id: int,
    to_account_id: int,
    amount_paise: int,
    tags: Optional[list[str]] = None,
) -> dict | str:
    """Create a double-entry transaction in the ledger.

    Args:
        type: payment | receipt | journal | contra
        date_str: ISO date string, e.g. "2026-05-16"
        narration: Description of the transaction
        fy_id: Financial year ID (get from get_active_fy)
        from_account_id: Source account ID (credit side — money leaves)
        to_account_id: Destination account ID (debit side — money arrives)
        amount_paise: Amount in paise (positive integer)
        tags: Optional list of tags
    """
    await emit("Creating transaction")
    entries = [
        {"account_id": from_account_id, "amount": -amount_paise},
        {"account_id": to_account_id, "amount": amount_paise},
    ]
    return await stow_post(
        ctx.deps,
        "/transactions",
        tool_name="create_transaction",
        json={
            "type": type,
            "date": date_str,
            "narration": narration,
            "fy_id": fy_id,
            "entries": entries,
            "tags": tags,
        },
    )


@tool_safe("list_transactions")
async def _list_transactions(
    ctx: RunContext[StowDeps],
    type: Optional[str] = None,
    account_id: Optional[int] = None,
    q: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
) -> list[dict] | str:
    """List transactions with optional filters.

    Args:
        type: Filter by type (payment | receipt | journal | contra)
        account_id: Filter by account involved in the transaction
        q: Search in narration (case-insensitive substring)
        from_date: Start date YYYY-MM-DD (inclusive)
        to_date: End date YYYY-MM-DD (inclusive)
    """
    await emit("Searching transactions")
    params: dict[str, Any] = {}
    if type:
        params["type"] = type
    if account_id:
        params["account_id"] = account_id
    if q:
        params["q"] = q
    if from_date:
        params["from_date"] = from_date
    if to_date:
        params["to_date"] = to_date
    return await stow_get(ctx.deps, "/transactions", tool_name="list_transactions", params=params)


@tool_safe("get_transaction")
async def _get_transaction(ctx: RunContext[StowDeps], txn_id: int) -> dict | str:
    """Fetch a single transaction by ID with all its entries.

    Args:
        txn_id: Transaction ID
    """
    await emit("Fetching transaction")
    return await stow_get(ctx.deps, f"/transactions/{txn_id}", tool_name="get_transaction")


@tool_safe("update_transaction")
async def _update_transaction(
    ctx: RunContext[StowDeps],
    txn_id: int,
    narration: Optional[str] = None,
    date_str: Optional[str] = None,
    tags: Optional[list[str]] = None,
) -> dict | str:
    """Update narration, date, or tags on an existing transaction.

    Args:
        txn_id: Transaction ID to update
        narration: New narration (optional)
        date_str: New ISO date string (optional)
        tags: New tags list (optional)
    """
    await emit("Updating transaction")
    body: dict[str, Any] = {}
    if narration is not None:
        body["narration"] = narration
    if date_str is not None:
        body["date"] = date_str
    if tags is not None:
        body["tags"] = tags
    return await stow_put(
        ctx.deps,
        f"/transactions/{txn_id}",
        tool_name="update_transaction",
        json=body,
    )


@tool_safe("delete_transaction")
async def _delete_transaction(ctx: RunContext[StowDeps], txn_id: int) -> dict | str:
    """Delete a transaction by ID.

    Note: Deleting a transaction that opened an investment (FD/MF/stock) cascades —
    it also deletes the associated Lot records, FdMetadata, and CapitalGainEntry records.

    Args:
        txn_id: Transaction ID to delete
    """
    await emit("Deleting transaction")
    result = await stow_delete(ctx.deps, f"/transactions/{txn_id}", tool_name="delete_transaction")
    if is_tool_error(result):
        return result
    return {"deleted": True, "txn_id": txn_id}


@tool_safe("get_depreciation_summary")
async def _get_depreciation_summary(
    ctx: RunContext[StowDeps],
    fy_id: int,
) -> dict | str:
    """Get WDV depreciation summary for a financial year.

    Returns per-asset depreciation amounts for year-end closing.
    Fixed assets carry a WDV rate (e.g., 40% for computers, 15% for furniture).
    Assets added after Oct 3 get 50% depreciation in year of acquisition (half-year rule).

    Args:
        fy_id: Financial year ID
    """
    await emit("Calculating depreciation")
    return await stow_get(
        ctx.deps,
        "/depreciation/summary",
        tool_name="get_depreciation_summary",
        params={"fy_id": fy_id},
    )


# ─── Investment Tools ────────────────────────────────────────────────────────

@tool_safe("create_fd")
async def _create_fd(
    ctx: RunContext[StowDeps],
    name: str,
    principal: int,
    interest_rate: int,
    start_date: str,
    maturity_date: str,
    compounding: str,
    from_account_id: int,
    fy_id: int,
    date: str,
    narration: Optional[str] = "",
) -> dict | str:
    """Open a fixed deposit and record the cash movement in the ledger.

    Args:
        name: FD name
        principal: Principal amount in paise
        interest_rate: Interest rate in basis points (e.g., 750 = 7.50% p.a.)
        start_date: Start date YYYY-MM-DD
        maturity_date: Maturity date YYYY-MM-DD
        compounding: monthly | quarterly | half_yearly | yearly
        from_account_id: Source bank account ID (money leaves)
        fy_id: Financial year ID
        date: Transaction date YYYY-MM-DD
        narration: Optional narration
    """
    await emit("Creating fixed deposit")
    return await stow_post(
        ctx.deps,
        "/investments/fds",
        tool_name="create_fd",
        json={
            "name": name,
            "principal": principal,
            "interest_rate": interest_rate,
            "start_date": start_date,
            "maturity_date": maturity_date,
            "compounding": compounding,
            "from_account_id": from_account_id,
            "fy_id": fy_id,
            "date": date,
            "narration": narration or "",
        },
    )


@tool_safe("mature_fd")
async def _mature_fd(
    ctx: RunContext[StowDeps],
    fd_account_id: int,
    to_account_id: int,
    fy_id: int,
    date: str,
    narration: Optional[str] = "",
) -> dict | str:
    """Process FD maturity: receive principal + interest, recognise interest income.

    Args:
        fd_account_id: FD account ID
        to_account_id: Bank account that receives proceeds
        fy_id: Financial year ID
        date: Transaction date YYYY-MM-DD
        narration: Optional narration
    """
    await emit("Processing FD maturity")
    return await stow_post(
        ctx.deps,
        f"/investments/fds/{fd_account_id}/mature",
        tool_name="mature_fd",
        json={
            "to_account_id": to_account_id,
            "fy_id": fy_id,
            "date": date,
            "narration": narration or "",
        },
    )


@tool_safe("list_fds")
async def _list_fds(ctx: RunContext[StowDeps]) -> list[dict] | str:
    """List all active fixed deposits with accrued interest."""
    await emit("Fetching fixed deposits")
    return await stow_get(ctx.deps, "/investments/fds", tool_name="list_fds")


@tool_safe("buy_investment")
async def _buy_investment(
    ctx: RunContext[StowDeps],
    account_id: int,
    fy_id: int,
    date: str,
    units: int,
    cost_per_unit: int,
    bank_account_id: int,
    narration: Optional[str] = "",
) -> dict | str:
    """Record a purchase of MF units or stock.

    Args:
        account_id: The INVESTMENT account ID (e.g. "Parag Parikh Flexi Cap") — money goes IN
        fy_id: Financial year ID
        date: Transaction date YYYY-MM-DD
        units: milliunits (actual_units × 1000, e.g. 12.345 units → 12345)
        cost_per_unit: NAV/price in paise per unit (NAV_rupees × 100, e.g. ₹810.45 → 81045)
        bank_account_id: The PAYING account ID (e.g. "HDFC Savings") — money comes OUT
        narration: Optional narration
    """
    await emit("Recording purchase")
    return await stow_post(
        ctx.deps,
        f"/investments/{account_id}/buy",
        tool_name="buy_investment",
        json={
            "fy_id": fy_id,
            "date": date,
            "units": units,
            "cost_per_unit": cost_per_unit,
            "bank_account_id": bank_account_id,
            "narration": narration or "",
        },
    )


@tool_safe("sell_investment")
async def _sell_investment(
    ctx: RunContext[StowDeps],
    account_id: int,
    fy_id: int,
    date: str,
    units: int,
    price_per_unit: int,
    bank_account_id: int,
    narration: Optional[str] = "",
) -> list[dict] | str:
    """Record a sale of MF units or stock (FIFO), credit the receiving account, book capital gains.

    Args:
        account_id: The INVESTMENT account ID
        fy_id: Financial year ID
        date: Transaction date YYYY-MM-DD
        units: milliunits to sell
        price_per_unit: Sale price in paise per unit
        bank_account_id: Bank account that receives the proceeds
        narration: Optional narration
    """
    await emit("Recording sale")
    return await stow_post(
        ctx.deps,
        f"/investments/{account_id}/sell",
        tool_name="sell_investment",
        json={
            "fy_id": fy_id,
            "date": date,
            "units": units,
            "price_per_unit": price_per_unit,
            "bank_account_id": bank_account_id,
            "narration": narration or "",
        },
    )


@tool_safe("get_holdings")
async def _get_holdings(ctx: RunContext[StowDeps], account_id: int) -> list[dict] | str:
    """Get current lot holdings for an investment account.

    Args:
        account_id: Investment account ID
    """
    await emit("Fetching holdings")
    return await stow_get(
        ctx.deps,
        f"/investments/{account_id}/holdings",
        tool_name="get_holdings",
    )


@tool_safe("get_portfolio")
async def _get_portfolio(ctx: RunContext[StowDeps], account_id: int) -> list[dict] | str:
    """Get portfolio with current value and unrealized gains (requires a price quote on file).

    Args:
        account_id: Investment account ID
    """
    await emit("Fetching portfolio")
    return await stow_get(
        ctx.deps,
        f"/investments/{account_id}/portfolio",
        tool_name="get_portfolio",
    )


@tool_safe("get_capital_gains")
async def _get_capital_gains(
    ctx: RunContext[StowDeps],
    account_id: int,
    fy_id: int,
) -> dict | str:
    """Get STCG/LTCG capital gains summary for an account in a financial year.

    Args:
        account_id: Investment account ID
        fy_id: Financial year ID
    """
    await emit("Calculating capital gains")
    return await stow_get(
        ctx.deps,
        f"/investments/{account_id}/capital-gains",
        tool_name="get_capital_gains",
        params={"fy_id": fy_id},
    )


@tool_safe("list_investment_accounts")
async def _list_investment_accounts(ctx: RunContext[StowDeps]) -> list[dict] | str:
    """List all investment accounts (equity_mf, stock, fd, ppf)."""
    await emit("Fetching investment accounts")
    accounts = await stow_get(ctx.deps, "/accounts", tool_name="list_investment_accounts")
    if is_tool_error(accounts):
        return accounts
    assert isinstance(accounts, list), f"Expected list of accounts, got {type(accounts)}"
    return [a for a in accounts if isinstance(a, dict) and a.get("investment_subtype")]


@tool_safe("fetch_prices")
async def _fetch_prices(ctx: RunContext[StowDeps]) -> dict | str:
    """Fetch latest market prices for all equity MF and stock investment accounts.

    This calls AMFI for MF NAVs and NSE bhavcopy/yfinance for stock prices.
    Required before portfolio shows current value and unrealized gains.
    """
    await emit("Fetching latest prices")
    return await stow_post(
        ctx.deps,
        "/prices/fetch",
        tool_name="fetch_prices",
    )


@tool_safe("get_tax_rules")
async def _get_tax_rules(ctx: RunContext[StowDeps]) -> list[dict] | str:
    """Get current capital gains tax rules (STCG/LTCG rates, holding periods, exemption).

    Tax rules are versioned — the active rule determines current-year tax calculations.
    """
    await emit("Fetching tax rules")
    return await stow_get(ctx.deps, "/tax-rules", tool_name="get_tax_rules")


# ─── Import Tools ────────────────────────────────────────────────────────────

@tool_safe("match_bank_account")
async def _match_bank_account(ctx: RunContext[StowDeps], batch_id: int) -> dict | None | str:
    """Match the batch detected_bank field to a ledger bank account.

    Args:
        batch_id: Import batch ID
    """
    await emit("Matching bank account")
    batch = await stow_get(ctx.deps, f"/imports/{batch_id}", tool_name="match_bank_account")
    if is_tool_error(batch):
        return batch
    assert isinstance(batch, dict), f"Expected batch dict, got {type(batch)}"
    accounts = await stow_get(ctx.deps, "/accounts", tool_name="match_bank_account")
    if is_tool_error(accounts):
        return accounts
    assert isinstance(accounts, list), f"Expected list of accounts, got {type(accounts)}"
    matched = match_bank_account(accounts, batch.get("detected_bank"))
    if matched is None:
        return None
    return {"id": matched["id"], "name": matched["name"], "detected_bank": batch.get("detected_bank")}


@tool_safe("review_staging")
async def _review_staging(
    ctx: RunContext[StowDeps],
    batch_id: int,
    status: Optional[str] = None,
) -> list[dict] | str:
    """List staging rows for a batch, optionally filtered by status.

    Args:
        batch_id: Import batch ID
        status: Filter by status: pending | confirmed | discarded | reconciled
    """
    await emit("Reviewing import batch")
    params: dict[str, Any] = {}
    if status:
        params["status"] = status
    return await stow_get(
        ctx.deps,
        f"/imports/{batch_id}/rows",
        tool_name="review_staging",
        params=params,
    )


@tool_safe("confirm_staging")
async def _confirm_staging(
    ctx: RunContext[StowDeps],
    batch_id: int,
    bank_account_id: int,
    fy_id: int,
) -> dict | str:
    """Post all confirmed staging rows as transactions.

    Args:
        batch_id: Import batch ID
        bank_account_id: Bank account ID for debit/credit entries
        fy_id: Financial year ID to post transactions into
    """
    await emit("Posting transactions")
    return await stow_post(
        ctx.deps,
        f"/imports/{batch_id}/confirm",
        tool_name="confirm_staging",
        json={"bank_account_id": bank_account_id, "fy_id": fy_id},
    )


@tool_safe("match_staging_row")
async def _match_staging_row(
    ctx: RunContext[StowDeps],
    batch_id: int,
    row_id: int,
    transaction_id: int,
) -> dict | str:
    """Mark a staging row as reconciled against an existing transaction.

    Args:
        batch_id: Import batch ID
        row_id: Staging row ID
        transaction_id: Existing transaction ID to match against
    """
    await emit("Reconciling transaction")
    return await stow_post(
        ctx.deps,
        f"/imports/{batch_id}/rows/{row_id}/match",
        tool_name="match_staging_row",
        json={"transaction_id": transaction_id},
    )


@tool_safe("update_staging_row")
async def _update_staging_row(
    ctx: RunContext[StowDeps],
    batch_id: int,
    row_id: int,
    status: Optional[str] = None,
    suggested_account_id: Optional[int] = None,
    narration_override: Optional[str] = None,
    tags: Optional[list[str]] = None,
) -> dict | str:
    """Update a staging row's status, account, or narration.

    Args:
        batch_id: Import batch ID
        row_id: Staging row ID
        status: New status: confirmed | discarded | pending
        suggested_account_id: Override suggested counterpart account
        narration_override: Override narration for this row
        tags: Tags to apply when confirmed
    """
    await emit("Updating staging row")
    body: dict[str, Any] = {}
    if status is not None:
        body["status"] = status
    if suggested_account_id is not None:
        body["suggested_account_id"] = suggested_account_id
    if narration_override is not None:
        body["narration_override"] = narration_override
    if tags is not None:
        body["tags"] = tags
    return await stow_put(
        ctx.deps,
        f"/imports/{batch_id}/rows/{row_id}",
        tool_name="update_staging_row",
        json=body,
    )


@tool_safe("get_batch")
async def _get_batch(ctx: RunContext[StowDeps], batch_id: int) -> dict | str:
    """Get import batch details including row counts by status.

    Args:
        batch_id: Import batch ID
    """
    await emit("Fetching import batch")
    return await stow_get(ctx.deps, f"/imports/{batch_id}", tool_name="get_batch")


@tool_safe("apply_merchant_rules")
async def _apply_merchant_rules(
    ctx: RunContext[StowDeps],
    batch_id: int,
    only_defaults: bool = False,
) -> dict | str:
    """Apply merchant rules to auto-match pending staging rows.

    Rows that match a saved merchant rule are automatically mapped.
    Use only_defaults=True to only apply default rules per account.

    Args:
        batch_id: Import batch ID
        only_defaults: Only apply default rules (default: False)
    """
    await emit("Applying merchant rules")
    return await stow_post(
        ctx.deps,
        f"/imports/{batch_id}/rows/apply-rules",
        tool_name="apply_merchant_rules",
        json={"only_defaults": only_defaults},
    )


# ─── Recurring Tools ─────────────────────────────────────────────────────────

@tool_safe("get_recurring_due")
async def _get_recurring_due(ctx: RunContext[StowDeps]) -> list[dict] | str:
    """Get all recurring transaction queue items due today."""
    await emit("Checking recurring items")
    return await stow_get(ctx.deps, "/recurring/due-today", tool_name="get_recurring_due")


@tool_safe("confirm_recurring")
async def _confirm_recurring(
    ctx: RunContext[StowDeps],
    item_id: int,
    date_override: Optional[str] = None,
    narration_override: Optional[str] = None,
) -> dict | str:
    """Post a recurring queue item as a transaction.

    Args:
        item_id: Recurring queue item ID
        date_override: ISO date override (default: due_date)
        narration_override: Narration override (default: template narration)
    """
    await emit("Posting recurring transaction")
    body: dict[str, Any] = {}
    if date_override:
        body["date"] = date_override
    if narration_override:
        body["narration"] = narration_override
    return await stow_post(
        ctx.deps,
        f"/recurring/queue/{item_id}/confirm",
        tool_name="confirm_recurring",
        json=body,
    )


@tool_safe("skip_recurring")
async def _skip_recurring(ctx: RunContext[StowDeps], item_id: int) -> dict | str:
    """Skip a recurring queue item without posting a transaction.

    Args:
        item_id: Recurring queue item ID
    """
    await emit("Skipping recurring item")
    return await stow_post(ctx.deps, f"/recurring/queue/{item_id}/skip", tool_name="skip_recurring")


@tool_safe("list_schedules")
async def _list_schedules(ctx: RunContext[StowDeps]) -> list[dict] | str:
    """List all active recurring schedules."""
    await emit("Fetching schedules")
    return await stow_get(ctx.deps, "/recurring/schedules", tool_name="list_schedules")


# ─── Report Tools ────────────────────────────────────────────────────────────

@tool_safe("get_trial_balance")
async def _get_trial_balance(ctx: RunContext[StowDeps], fy_id: int) -> dict | str:
    """Get the trial balance for a financial year.

    Args:
        fy_id: Financial year ID
    """
    await emit("Generating trial balance")
    return await stow_get(
        ctx.deps,
        "/reports/trial-balance",
        tool_name="get_trial_balance",
        params={"fy_id": fy_id},
    )


@tool_safe("get_profit_loss")
async def _get_profit_loss(ctx: RunContext[StowDeps], fy_id: int) -> dict | str:
    """Get the profit & loss report for a financial year.

    Args:
        fy_id: Financial year ID
    """
    await emit("Generating P&L report")
    return await stow_get(
        ctx.deps,
        "/reports/profit-loss",
        tool_name="get_profit_loss",
        params={"fy_id": fy_id},
    )


@tool_safe("get_balance_sheet")
async def _get_balance_sheet(ctx: RunContext[StowDeps], fy_id: int) -> dict | str:
    """Get the balance sheet for a financial year.

    Args:
        fy_id: Financial year ID
    """
    await emit("Generating balance sheet")
    return await stow_get(
        ctx.deps,
        "/reports/balance-sheet",
        tool_name="get_balance_sheet",
        params={"fy_id": fy_id},
    )


@tool_safe("get_cash_flow")
async def _get_cash_flow(ctx: RunContext[StowDeps], fy_id: int) -> dict | str:
    """Get the cash flow statement for a financial year.

    Args:
        fy_id: Financial year ID
    """
    await emit("Generating cash flow statement")
    return await stow_get(
        ctx.deps,
        "/reports/cash-flow",
        tool_name="get_cash_flow",
        params={"fy_id": fy_id},
    )


# ─── UPI / Merchant Tools ────────────────────────────────────────────────────

@tool_safe("get_merchant_rules")
async def _get_merchant_rules(ctx: RunContext[StowDeps]) -> list[dict] | str:
    """Return merchant matching rules for UPI/payment account pre-fill.

    Each rule has a pattern (case-insensitive substring, e.g. "zomato") and an account_id.
    Call this when processing a payment screenshot to check if the merchant name matches
    any rule and pre-fill the account before creating the transaction.
    """
    await emit("Looking up merchant rules")
    rules = await stow_get(ctx.deps, "/merchant-rules", tool_name="get_merchant_rules")
    if is_tool_error(rules):
        return rules
    assert isinstance(rules, list), f"Expected list of rules, got {type(rules)}"
    return rules


@tool_safe("resolve_upi_accounts")
async def _resolve_upi_accounts(
    ctx: RunContext[StowDeps],
    payee_name: str,
    source_bank_name: str = "",
    source_account_last4: str = "",
) -> dict | str:
    """Match payee and source bank from a UPI screenshot to ledger account IDs.

    Call this after extracting payment details from an image. Returns from_account and
    to_account dicts (id, name) when matched against bank/expense accounts and merchant rules.

    Args:
        payee_name: Merchant/payee name extracted from the screenshot
        source_bank_name: Source bank name (e.g. "Axis Bank", "HDFC")
        source_account_last4: Last 4 digits of source account (if visible)
    """
    await emit("Matching accounts")
    accounts = await stow_get(ctx.deps, "/accounts", tool_name="resolve_upi_accounts")
    if is_tool_error(accounts):
        return accounts
    assert isinstance(accounts, list), f"Expected list of accounts, got {type(accounts)}"
    rules = await _get_merchant_rules(ctx)
    if is_tool_error(rules):
        return rules
    assert isinstance(rules, list), f"Expected list of rules, got {type(rules)}"
    result = resolve_upi_accounts(
        accounts,
        rules,
        payee_name=payee_name,
        source_bank_name=source_bank_name or None,
        source_account_last4=source_account_last4 or None,
    )
    return {
        "from_account": (
            {"id": result["from_account"]["id"], "name": result["from_account"]["name"]}
            if result["from_account"]
            else None
        ),
        "to_account": (
            {"id": result["to_account"]["id"], "name": result["to_account"]["name"]}
            if result["to_account"]
            else None
        ),
        "fully_resolved": result["fully_resolved"],
    }


@tool_safe("create_merchant_rule")
async def _create_merchant_rule(
    ctx: RunContext[StowDeps],
    pattern: str,
    account_id: int,
    default_for_account: bool = False,
) -> dict | str:
    """Create a merchant matching rule for auto-matching bank imports.

    The pattern is a case-insensitive substring match with optional wildcard (*).
    E.g., "zomato" matches any description containing "zomato".

    Args:
        pattern: Wildcard pattern to match against merchant names
        account_id: Target account ID to map to
        default_for_account: Set as default rule for this account
    """
    await emit("Creating merchant rule")
    body: dict[str, Any] = {"pattern": pattern, "account_id": account_id}
    if default_for_account:
        body["default_for_account"] = default_for_account
    return await stow_post(
        ctx.deps,
        "/merchant-rules",
        tool_name="create_merchant_rule",
        json=body,
    )


@tool_safe("delete_merchant_rule")
async def _delete_merchant_rule(ctx: RunContext[StowDeps], rule_id: int) -> dict | str:
    """Delete a merchant matching rule.

    Args:
        rule_id: Rule ID to delete
    """
    await emit("Deleting merchant rule")
    return await stow_delete(
        ctx.deps,
        f"/merchant-rules/{rule_id}",
        tool_name="delete_merchant_rule",
    )


# ─── Proposal Tools ──────────────────────────────────────────────────────────

@tool_safe("post_confirmed_proposal")
async def _post_confirmed_proposal(ctx: RunContext[StowDeps], proposal_json: str) -> dict | str:
    """Post a confirmed transaction proposal JSON to the ledger.

    Args:
        proposal_json: Full PROPOSAL JSON with type, date, amount_paise, narration,
                       from_account_id, from_account_name, to_account_id, to_account_name,
                       fy_id, and optional tags.
    """
    await emit("Confirming transaction")
    try:
        raw = json.loads(proposal_json)
    except json.JSONDecodeError as exc:
        return f"Error: post_confirmed_proposal failed: Invalid JSON — {exc}"
    result = await execute_proposal(raw, ctx.deps.http_client, ctx.deps.base_url)
    if isinstance(result, str):
        return result
    return {
        "posted": True,
        "number": result.get("number"),
        "narration": result.get("narration"),
        "message": format_post_success(result),
    }


# ─── Build ───────────────────────────────────────────────────────────────────

def build_agent() -> Agent[StowDeps, str]:
    """Build the unified Stow agent with all tools exposed at the top level."""
    model = build_model()

    return Agent(
        model=model,
        deps_type=StowDeps,
        instructions=_SYSTEM_PROMPT,
        tools=[
            # Shared
            _get_current_datetime,
            _get_active_fy,
            _get_fy_for_date,
            _get_financial_years,
            # Accounts
            _list_accounts,
            _get_account,
            _create_account,
            _archive_account,
            _get_account_ledger,
            _get_opening_balance,
            _set_opening_balance,
            # Transactions
            _parse_natural_language,
            _create_transaction,
            _list_transactions,
            _get_transaction,
            _update_transaction,
            _delete_transaction,
            _get_depreciation_summary,
            # Investments
            _create_fd,
            _mature_fd,
            _list_fds,
            _buy_investment,
            _sell_investment,
            _get_holdings,
            _get_portfolio,
            _get_capital_gains,
            _list_investment_accounts,
            _fetch_prices,
            _get_tax_rules,
            # Imports
            _match_bank_account,
            _review_staging,
            _confirm_staging,
            _match_staging_row,
            _update_staging_row,
            _get_batch,
            _apply_merchant_rules,
            # Recurring
            _get_recurring_due,
            _confirm_recurring,
            _skip_recurring,
            _list_schedules,
            # Reports
            _get_trial_balance,
            _get_profit_loss,
            _get_balance_sheet,
            _get_cash_flow,
            # UPI / Merchant
            _get_merchant_rules,
            _resolve_upi_accounts,
            _create_merchant_rule,
            _delete_merchant_rule,
            # Proposal
            _post_confirmed_proposal,
        ],
    )


# Backwards compat — the old name
build_orchestrator = build_agent
