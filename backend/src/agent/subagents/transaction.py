from __future__ import annotations

import json
from typing import Any, Optional

from pydantic_ai import Agent, RunContext

from agent.activity import emit
from agent.deps import StowDeps
from agent.tool_errors import is_tool_error, stow_delete, stow_get, stow_post, stow_put, tool_safe

_INSTRUCTIONS = """\
You are the transaction agent for an Indian personal finance system.
You parse, create, query, update, and delete double-entry transactions.

Key rules:
- All amounts are in paise (1 INR = 100 paise). Amounts like "₹500" = 50000 paise.
- Transaction types: payment | receipt | journal | contra
- from_account = credited account (money leaves, e.g. bank on a payment)
- to_account = debited account (money arrives, e.g. expense on a payment)

When any tool returns a string starting with "Error:", read the message, fix the issue,
retry with corrected inputs, or ask the user one clarifying question.

## CRITICAL: Proposal-first flow for new transactions — NEVER skip this

When asked to record a new transaction from natural language or extracted image data:
  1. Call get_active_fy → note the fy_id.
  2. Call list_accounts → note account names for the two accounts involved.
  3. Call parse_natural_language with the description text.
  4. Combine the result into this exact JSON and return it as your output — then STOP:
     {"type":"<type>","date":"<ISO date>","amount_paise":<int>,"narration":"<str>",
      "from_account_id":<int>,"from_account_name":"<str>",
      "to_account_id":<int>,"to_account_name":"<str>","fy_id":<int>,
      "tags":["<optional>","<tags>"]}
     Note: parse_natural_language returns the field as "amount" (in paise) — rename it to "amount_paise".
     Include tags from parse_natural_language when present; omit the tags key when empty.

Do NOT call create_transaction during this step. The orchestrator will show the user a
proposal card and re-invoke you with "confirm: <proposal JSON>" after the user approves.

Only call create_transaction when the message explicitly starts with "confirm:" AND provides
all required fields. In that case, skip steps 1–4 and call create_transaction directly using
the provided values. If create_transaction returns an Error string, diagnose and retry.

## NEVER handle investment operations
Do NOT process requests to buy/sell mutual funds, stocks, or open/mature fixed deposits.
These MUST go to investment_agent. If such a request reaches you, respond:
"This is an investment operation — please use investment_agent."

## Queries, updates, deletes
- Queries: use list_transactions or get_transaction and return results.
- Updates: use update_transaction with the specified changes.
- Deletes: use delete_transaction after confirming the txn_id.

Always return a structured summary of what was done.
"""


@tool_safe("get_active_fy")
async def _get_active_fy(ctx: RunContext[StowDeps]) -> dict | str:
    """Get the currently active financial year."""
    await emit("Looking up financial year")
    fys = await stow_get(ctx.deps, "/financial-years", tool_name="get_active_fy")
    if is_tool_error(fys):
        return fys
    active = next((fy for fy in fys if fy["status"] == "active"), None)
    if not active:
        active = next((fy for fy in fys if fy["status"] == "open"), None)
    return active or {}


@tool_safe("list_accounts")
async def _list_accounts(ctx: RunContext[StowDeps], include_archived: bool = False) -> list[dict] | str:
    """List all accounts with their current balances."""
    await emit("Fetching accounts")
    return await stow_get(
        ctx.deps,
        "/accounts",
        tool_name="list_accounts",
        params={"include_archived": include_archived},
    )


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
) -> list[dict] | str:
    """List transactions with optional filters.

    Args:
        type: Filter by type (payment | receipt | journal | contra)
        account_id: Filter by account ID
        q: Search in narration (case-insensitive substring)
    """
    await emit("Searching transactions")
    params: dict[str, Any] = {}
    if type:
        params["type"] = type
    if account_id:
        params["account_id"] = account_id
    if q:
        params["q"] = q
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

    Args:
        txn_id: Transaction ID to delete
    """
    await emit("Deleting transaction")
    result = await stow_delete(ctx.deps, f"/transactions/{txn_id}", tool_name="delete_transaction")
    if is_tool_error(result):
        return result
    return {"deleted": True, "txn_id": txn_id}


def build_transaction_agent(model: Any) -> Agent[StowDeps, str]:
    return Agent(
        model=model,
        deps_type=StowDeps,
        instructions=_INSTRUCTIONS,
        tools=[
            _get_active_fy,
            _list_accounts,
            _parse_natural_language,
            _create_transaction,
            _list_transactions,
            _get_transaction,
            _update_transaction,
            _delete_transaction,
        ],
    )
