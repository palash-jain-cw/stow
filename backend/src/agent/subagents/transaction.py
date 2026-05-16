from __future__ import annotations

from typing import Any, Optional

from pydantic_ai import Agent, RunContext

from agent.deps import StowDeps

_INSTRUCTIONS = """\
You are the transaction agent for an Indian personal finance system.
You parse, create, query, update, and delete double-entry transactions.

Key rules:
- All amounts are in paise (1 INR = 100 paise). Amounts like "₹500" = 50000 paise.
- Transaction types: payment | receipt | journal | contra
- Every transaction needs a from_account and to_account (expressed as entries summing to zero).
- Use get_active_fy to find the active financial year before creating a transaction.
- Use list_accounts to resolve account names to IDs.
- Always return a structured summary of what was done.
"""


async def _get_active_fy(ctx: RunContext[StowDeps]) -> dict:
    """Get the currently active financial year."""
    r = await ctx.deps.http_client.get(f"{ctx.deps.base_url}/financial-years")
    r.raise_for_status()
    fys = r.json()
    active = next((fy for fy in fys if fy["status"] == "active"), None)
    if not active:
        active = next((fy for fy in fys if fy["status"] == "open"), None)
    return active or {}


async def _list_accounts(ctx: RunContext[StowDeps], include_archived: bool = False) -> list[dict]:
    """List all accounts with their current balances."""
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
        from_account_id: Source account ID (debit side)
        to_account_id: Destination account ID (credit side)
        amount_paise: Amount in paise (positive integer)
        tags: Optional list of tags
    """
    entries = [
        {"account_id": from_account_id, "amount": amount_paise},
        {"account_id": to_account_id, "amount": -amount_paise},
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
