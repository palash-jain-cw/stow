from __future__ import annotations

from typing import Any, Optional

from pydantic_ai import Agent, RunContext

from agent.deps import StowDeps

_INSTRUCTIONS = """\
You are the recurring agent for an Indian personal finance system (Stow).
You manage the daily recurring transaction digest.

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


async def _get_recurring_due(ctx: RunContext[StowDeps]) -> list[dict]:
    """Get all recurring transaction queue items due today."""
    r = await ctx.deps.http_client.get(f"{ctx.deps.base_url}/recurring/due-today")
    r.raise_for_status()
    return r.json()


async def _confirm_recurring(
    ctx: RunContext[StowDeps],
    item_id: int,
    date_override: Optional[str] = None,
    narration_override: Optional[str] = None,
) -> dict:
    """Post a recurring queue item as a transaction.

    Args:
        item_id: Recurring queue item ID
        date_override: ISO date override (default: due_date)
        narration_override: Narration override (default: template narration)
    """
    body: dict[str, Any] = {}
    if date_override:
        body["date"] = date_override
    if narration_override:
        body["narration"] = narration_override
    r = await ctx.deps.http_client.post(
        f"{ctx.deps.base_url}/recurring/queue/{item_id}/confirm",
        json=body,
    )
    r.raise_for_status()
    return r.json()


async def _skip_recurring(ctx: RunContext[StowDeps], item_id: int) -> dict:
    """Skip a recurring queue item without posting a transaction.

    Args:
        item_id: Recurring queue item ID
    """
    r = await ctx.deps.http_client.post(
        f"{ctx.deps.base_url}/recurring/queue/{item_id}/skip",
    )
    r.raise_for_status()
    return r.json()


async def _list_schedules(ctx: RunContext[StowDeps]) -> list[dict]:
    """List all active recurring schedules."""
    r = await ctx.deps.http_client.get(f"{ctx.deps.base_url}/recurring/schedules")
    r.raise_for_status()
    return r.json()


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
