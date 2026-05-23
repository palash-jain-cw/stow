from __future__ import annotations

from typing import Any, Optional

from pydantic_ai import Agent, RunContext

from agent.activity import emit
from agent.deps import StowDeps
from agent.subagents.transaction import _get_active_fy, _list_accounts
from agent.tool_errors import stow_get, stow_post, stow_put, tool_safe

_INSTRUCTIONS = """\
You are the import agent for an Indian personal finance system.
The bank statement PDF has already been parsed. You receive a batch_id from the orchestrator.

When any tool returns a string starting with "Error:", read the message, fix the issue,
retry, or ask the user one clarifying question.

Workflow:
1. Call review_staging(batch_id) to see all parsed rows.
2. Auto-confirm every row where possible_duplicate=False by calling
   update_staging_row(batch_id, row_id, status="confirmed") for each.
3. For each row where possible_duplicate=True, show the user ONE AT A TIME:
     "📋 {date} · {description} · ₹{amount/100:,.2f} — possible duplicate.
      Reply 'confirm anyway', 'skip', or 'view existing' (txn #{matched_transaction_id})."
   Wait for their reply before moving to the next duplicate.
   - 'confirm anyway' → update_staging_row(batch_id, row_id, status="confirmed")
   - 'skip' → update_staging_row(batch_id, row_id, status="discarded")
4. Call list_accounts to let the user pick a bank account, then call get_active_fy.
5. Call confirm_staging(batch_id, bank_account_id, fy_id).
6. Report: "✅ {posted} transactions posted. {reconciled} reconciled. {skipped} skipped."

Rules:
- Display amounts as ₹X,XX,XXX (Indian comma format).
- Display dates as DD Mon YYYY.
- Never call confirm_staging without first having both bank_account_id and fy_id confirmed.
"""


@tool_safe("import_statement")
async def _import_statement(
    ctx: RunContext[StowDeps],
    pdf_bytes_b64: str,
    filename: str,
) -> dict | str:
    """Upload a bank statement PDF and parse it into a staging batch.

    Args:
        pdf_bytes_b64: Base64-encoded PDF file bytes
        filename: Original filename (must end in .pdf)
    """
    import base64

    pdf_bytes = base64.b64decode(pdf_bytes_b64)
    return await stow_post(
        ctx.deps,
        "/imports",
        tool_name="import_statement",
        files={"file": (filename, pdf_bytes, "application/pdf")},
    )


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


def build_import_agent(model: Any) -> Agent[StowDeps, str]:
    return Agent(
        model=model,
        deps_type=StowDeps,
        instructions=_INSTRUCTIONS,
        tools=[
            _get_active_fy,
            _list_accounts,
            _review_staging,
            _confirm_staging,
            _match_staging_row,
            _update_staging_row,
            _get_batch,
        ],
    )
