from __future__ import annotations

from typing import Any, Optional

from pydantic_ai import Agent, RunContext

from agent.activity import emit
from agent.deps import StowDeps

_INSTRUCTIONS = """\
You are the transaction agent for an Indian personal finance system.
You parse, create, query, update, and delete double-entry transactions.

Key rules:
- All amounts are in paise (1 INR = 100 paise). Amounts like "₹500" = 50000 paise.
- Transaction types: payment | receipt | journal | contra
- from_account = credited account (money leaves, e.g. bank on a payment)
- to_account = debited account (money arrives, e.g. expense on a payment)

## CRITICAL: Proposal-first flow for new transactions — NEVER skip this

When asked to record a new transaction from natural language or extracted image data:
  1. Call get_active_fy → note the fy_id.
  2. Call list_accounts → note account names for the two accounts involved.
  3. Call parse_natural_language with the description text.
  4. Combine the result into this exact JSON and return it as your output — then STOP:
     {"type":"<type>","date":"<ISO date>","amount_paise":<int>,"narration":"<str>",
      "from_account_id":<int>,"from_account_name":"<str>",
      "to_account_id":<int>,"to_account_name":"<str>","fy_id":<int>}
     Note: parse_natural_language returns the field as "amount" (in paise) — rename it to "amount_paise".

Do NOT call create_transaction during this step. The orchestrator will show the user a
proposal card and re-invoke you with "confirm: <proposal JSON>" after the user approves.

Only call create_transaction when the message explicitly starts with "confirm:" AND provides
all required fields. In that case, skip steps 1–4 and call create_transaction directly using
the provided values.

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


async def _get_active_fy(ctx: RunContext[StowDeps]) -> dict:
    """Get the currently active financial year."""
    await emit("Looking up financial year")
    r = await ctx.deps.http_client.get(f"{ctx.deps.base_url}/financial-years")
    r.raise_for_status()
    fys = r.json()
    active = next((fy for fy in fys if fy["status"] == "active"), None)
    if not active:
        active = next((fy for fy in fys if fy["status"] == "open"), None)
    return active or {}


async def _list_accounts(ctx: RunContext[StowDeps], include_archived: bool = False) -> list[dict]:
    """List all accounts with their current balances."""
    await emit("Fetching accounts")
    r = await ctx.deps.http_client.get(
        f"{ctx.deps.base_url}/accounts",
        params={"include_archived": include_archived},
    )
    r.raise_for_status()
    return r.json()


async def _parse_natural_language(ctx: RunContext[StowDeps], text: str) -> dict:
    """Parse a natural language transaction description into a structured proposal.

    Args:
        text: Natural language description, e.g. "paid electricity 2400 from HDFC last Tuesday"

    Returns:
        Structured transaction with type, date, amount_paise, narration, from_account_id, to_account_id.
    """
    await emit("Parsing transaction")
    r = await ctx.deps.http_client.post(
        f"{ctx.deps.base_url}/ai/parse-transaction",
        json={"text": text},
    )
    r.raise_for_status()
    return r.json()


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
) -> dict:
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
    r = await ctx.deps.http_client.post(
        f"{ctx.deps.base_url}/transactions",
        json={
            "type": type,
            "date": date_str,
            "narration": narration,
            "fy_id": fy_id,
            "entries": entries,
            "tags": tags,
        },
    )
    r.raise_for_status()
    return r.json()


async def _list_transactions(
    ctx: RunContext[StowDeps],
    type: Optional[str] = None,
    account_id: Optional[int] = None,
    q: Optional[str] = None,
) -> list[dict]:
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
    r = await ctx.deps.http_client.get(f"{ctx.deps.base_url}/transactions", params=params)
    r.raise_for_status()
    return r.json()


async def _get_transaction(ctx: RunContext[StowDeps], txn_id: int) -> dict:
    """Fetch a single transaction by ID with all its entries.

    Args:
        txn_id: Transaction ID
    """
    await emit("Fetching transaction")
    r = await ctx.deps.http_client.get(f"{ctx.deps.base_url}/transactions/{txn_id}")
    r.raise_for_status()
    return r.json()


async def _update_transaction(
    ctx: RunContext[StowDeps],
    txn_id: int,
    narration: Optional[str] = None,
    date_str: Optional[str] = None,
    tags: Optional[list[str]] = None,
) -> dict:
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
    r = await ctx.deps.http_client.put(f"{ctx.deps.base_url}/transactions/{txn_id}", json=body)
    r.raise_for_status()
    return r.json()


async def _delete_transaction(ctx: RunContext[StowDeps], txn_id: int) -> dict:
    """Delete a transaction by ID.

    Args:
        txn_id: Transaction ID to delete
    """
    await emit("Deleting transaction")
    r = await ctx.deps.http_client.delete(f"{ctx.deps.base_url}/transactions/{txn_id}")
    r.raise_for_status()
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
