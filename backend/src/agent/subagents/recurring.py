from __future__ import annotations

from typing import Any, Optional

from pydantic_ai import Agent, RunContext

from agent.deps import StowDeps

_INSTRUCTIONS = """\
You are the recurring agent for an Indian personal finance system.
You process recurring transaction schedules.

Workflow for /recurring:
1. get_recurring_due — fetch all items due today
2. Present each item to the user with [Confirm] [Skip] [Edit] options
3. confirm_recurring or skip_recurring based on user choice

Each item in the queue corresponds to a recurring schedule.
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
