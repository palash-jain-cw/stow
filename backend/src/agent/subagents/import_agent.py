from __future__ import annotations

from typing import Any, Optional

from pydantic_ai import Agent, RunContext

from agent.deps import StowDeps

_INSTRUCTIONS = """\
You are the import agent for an Indian personal finance system.
You handle bank statement PDF uploads, staging review, and confirmation.

Workflow:
1. import_statement — upload PDF → returns batch with parsed rows
2. review_staging — list rows, noting status (pending | confirmed | discarded) and possible_duplicate flag
3. Auto-confirm non-duplicate rows via update_staging_row (set status="confirmed")
4. Surface only flagged duplicates for user review
5. confirm_staging — post all confirmed rows as transactions

Always ask for bank_account_id and fy_id before calling confirm_staging.
"""


async def _import_statement(
    ctx: RunContext[StowDeps],
    pdf_bytes_b64: str,
    filename: str,
) -> dict:
    """Upload a bank statement PDF and parse it into a staging batch.

    Args:
        pdf_bytes_b64: Base64-encoded PDF file bytes
        filename: Original filename (must end in .pdf)
    """
    import base64
    pdf_bytes = base64.b64decode(pdf_bytes_b64)
    r = await ctx.deps.http_client.post(
        f"{ctx.deps.base_url}/imports",
        files={"file": (filename, pdf_bytes, "application/pdf")},
    )
    r.raise_for_status()
    return r.json()


async def _review_staging(
    ctx: RunContext[StowDeps],
    batch_id: int,
    status: Optional[str] = None,
) -> list[dict]:
    """List staging rows for a batch, optionally filtered by status.

    Args:
        batch_id: Import batch ID
        status: Filter by status: pending | confirmed | discarded | reconciled
    """
    params: dict[str, Any] = {}
    if status:
        params["status"] = status
    r = await ctx.deps.http_client.get(
        f"{ctx.deps.base_url}/imports/{batch_id}/rows",
        params=params,
    )
    r.raise_for_status()
    return r.json()


async def _confirm_staging(
    ctx: RunContext[StowDeps],
    batch_id: int,
    bank_account_id: int,
    fy_id: int,
) -> dict:
    """Post all confirmed staging rows as transactions.

    Args:
        batch_id: Import batch ID
        bank_account_id: Bank account ID for debit/credit entries
        fy_id: Financial year ID to post transactions into
    """
    r = await ctx.deps.http_client.post(
        f"{ctx.deps.base_url}/imports/{batch_id}/confirm",
        json={"bank_account_id": bank_account_id, "fy_id": fy_id},
    )
    r.raise_for_status()
    return r.json()


async def _match_staging_row(
    ctx: RunContext[StowDeps],
    batch_id: int,
    row_id: int,
    transaction_id: int,
) -> dict:
    """Mark a staging row as reconciled against an existing transaction.

    Args:
        batch_id: Import batch ID
        row_id: Staging row ID
        transaction_id: Existing transaction ID to match against
    """
    r = await ctx.deps.http_client.post(
        f"{ctx.deps.base_url}/imports/{batch_id}/rows/{row_id}/match",
        json={"transaction_id": transaction_id},
    )
    r.raise_for_status()
    return r.json()


async def _update_staging_row(
    ctx: RunContext[StowDeps],
    batch_id: int,
    row_id: int,
    status: Optional[str] = None,
    suggested_account_id: Optional[int] = None,
    narration_override: Optional[str] = None,
    tags: Optional[list[str]] = None,
) -> dict:
    """Update a staging row's status, account, or narration.

    Args:
        batch_id: Import batch ID
        row_id: Staging row ID
        status: New status: confirmed | discarded | pending
        suggested_account_id: Override suggested counterpart account
        narration_override: Override narration for this row
        tags: Tags to apply when confirmed
    """
    body: dict[str, Any] = {}
    if status is not None:
        body["status"] = status
    if suggested_account_id is not None:
        body["suggested_account_id"] = suggested_account_id
    if narration_override is not None:
        body["narration_override"] = narration_override
    if tags is not None:
        body["tags"] = tags
    r = await ctx.deps.http_client.put(
        f"{ctx.deps.base_url}/imports/{batch_id}/rows/{row_id}",
        json=body,
    )
    r.raise_for_status()
    return r.json()


async def _get_batch(ctx: RunContext[StowDeps], batch_id: int) -> dict:
    """Get import batch details including row counts by status.

    Args:
        batch_id: Import batch ID
    """
    r = await ctx.deps.http_client.get(f"{ctx.deps.base_url}/imports/{batch_id}")
    r.raise_for_status()
    return r.json()


def build_import_agent(model: Any) -> Agent[StowDeps, str]:
    return Agent(
        model=model,
        deps_type=StowDeps,
        instructions=_INSTRUCTIONS,
        tools=[
            _import_statement,
            _review_staging,
            _confirm_staging,
            _match_staging_row,
            _update_staging_row,
            _get_batch,
        ],
    )
