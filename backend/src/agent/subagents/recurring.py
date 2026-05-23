from __future__ import annotations

from typing import Any, Optional

from pydantic_ai import Agent, RunContext

from agent.activity import emit
from agent.deps import StowDeps
from agent.tool_errors import stow_get, stow_post, tool_safe

_INSTRUCTIONS = """\
You are the recurring agent for an Indian personal finance system (Stow).
You manage the daily recurring transaction digest.

When any tool returns a string starting with "Error:", read the message, fix the issue,
retry, or ask the user one clarifying question.

## Workflow
1. Call get_recurring_due to fetch all items due today.
2. If none are due, reply: "No recurring transactions due today."
3. If items exist, present a numbered digest — one card per item:

   1. Monthly rent — ₹50,000
      From: HDFC Bank → To: Rent Expense
      Reply "confirm 1" to post, "skip 1" to skip.

4. When the user replies "confirm N", call confirm_recurring with that item's id.
   When the user replies "skip N", call skip_recurring with that item's id.
5. After each action, confirm it: "✓ Monthly rent posted (PAY-2026-001)" or "Skipped."
6. Once all items are handled, send a summary: "Done — X confirmed, Y skipped."

## Formatting
- Amounts: ₹X,XX,XXX (Indian commas; divide paise by 100).
- Keep cards concise — narration, amount, from → to accounts, action hint.
"""


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


def build_recurring_agent(model: Any) -> Agent[StowDeps, str]:
    return Agent(
        model=model,
        deps_type=StowDeps,
        instructions=_INSTRUCTIONS,
        tools=[
            _get_recurring_due,
            _confirm_recurring,
            _skip_recurring,
            _list_schedules,
        ],
    )
