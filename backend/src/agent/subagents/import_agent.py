from __future__ import annotations

from typing import Any, Optional

from pydantic_ai import Agent, RunContext

from agent.activity import emit
from agent.deps import StowDeps
from agent.subagents.transaction import _get_active_fy, _list_accounts
from agent.tool_errors import is_tool_error, stow_get, stow_post, stow_put, tool_safe
from stow.import_pipeline import match_bank_account

_INSTRUCTIONS = """\
You are the import agent for an Indian personal finance system.
The bank statement PDF has already been parsed. You receive a batch_id from the orchestrator.

When any tool returns a string starting with "Error:", read the message, fix the issue,
retry, or ask the user one clarifying question.

Workflow:
1. Call get_batch(batch_id) for row counts and detected_bank.
2. Call review_staging(batch_id) to see all parsed rows.
3. Auto-confirm ONLY rows where possible_duplicate=False AND suggested_account_id is set:
     update_staging_row(batch_id, row_id, status="confirmed")
   For rows without suggested_account_id, ask the user which account to use (ONE question
   listing all unmapped descriptions), then update_staging_row with suggested_account_id
   and status="confirmed".
4. For each row where possible_duplicate=True, show the user ONE AT A TIME:
     "📋 {date} · {description} · ₹{amount/100:,.2f} — possible duplicate.
      Reply 'confirm anyway', 'skip', or 'view existing' (txn #{matched_transaction_id})."
   Wait for their reply before moving to the next duplicate.
5. Call match_bank_account(batch_id). If it returns null, call list_accounts and ask which
   bank account this statement belongs to. Otherwise use the matched bank_account_id.
6. Call get_active_fy for fy_id (active financial year — bank imports should be current FY).
7. Call confirm_staging(batch_id, bank_account_id, fy_id).
8. Report using confirm_staging response fields:
     posted_count, skipped_count, and any skipped reasons.

Rules:
- Display amounts as ₹X,XX,XXX (Indian comma format).
- Display dates as DD Mon YYYY.
- Never call confirm_staging without bank_account_id and fy_id.
- Never confirm rows without suggested_account_id — they cannot post correctly.
- Rows dated outside the active FY or in a locked FY will be skipped at post time; warn the user.
"""


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
    accounts = await stow_get(ctx.deps, "/accounts", tool_name="match_bank_account")
    if is_tool_error(accounts):
        return accounts
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


def build_import_agent(model: Any) -> Agent[StowDeps, str]:
    return Agent(
        model=model,
        deps_type=StowDeps,
        instructions=_INSTRUCTIONS,
        tools=[
            _get_active_fy,
            _list_accounts,
            _match_bank_account,
            _review_staging,
            _confirm_staging,
            _match_staging_row,
            _update_staging_row,
            _get_batch,
        ],
    )
