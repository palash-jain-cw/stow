from __future__ import annotations

from typing import Any

from pydantic_ai import Agent, RunContext

from agent.deps import StowDeps

_INSTRUCTIONS = """\
You are the report agent for an Indian personal finance system.
You answer financial queries and generate reports.

Available reports: trial balance, profit & loss, balance sheet, cash flow.
All reports require a financial year ID (fy_id). Use get_financial_years to find it.

For balance queries, use get_accounts from the account agent context or infer from reports.
For spending queries, use profit_loss or trial_balance filtered by account.
"""


async def _get_financial_years(ctx: RunContext[StowDeps]) -> list[dict]:
    """List all financial years with their status (open | active | locked)."""
    r = await ctx.deps.http_client.get(f"{ctx.deps.base_url}/financial-years")
    r.raise_for_status()
    return r.json()


async def _get_trial_balance(ctx: RunContext[StowDeps], fy_id: int) -> dict:
    """Get the trial balance report for a financial year.

    Args:
        fy_id: Financial year ID
    """
    r = await ctx.deps.http_client.get(
        f"{ctx.deps.base_url}/reports/trial-balance",
        params={"fy_id": fy_id},
    )
    r.raise_for_status()
    return r.json()


async def _get_profit_loss(ctx: RunContext[StowDeps], fy_id: int) -> dict:
    """Get the profit & loss report for a financial year.

    Args:
        fy_id: Financial year ID
    """
    r = await ctx.deps.http_client.get(
        f"{ctx.deps.base_url}/reports/profit-loss",
        params={"fy_id": fy_id},
    )
    r.raise_for_status()
    return r.json()


async def _get_balance_sheet(ctx: RunContext[StowDeps], fy_id: int) -> dict:
    """Get the balance sheet for a financial year.

    Args:
        fy_id: Financial year ID
    """
    r = await ctx.deps.http_client.get(
        f"{ctx.deps.base_url}/reports/balance-sheet",
        params={"fy_id": fy_id},
    )
    r.raise_for_status()
    return r.json()


async def _get_cash_flow(ctx: RunContext[StowDeps], fy_id: int) -> dict:
    """Get the cash flow statement for a financial year.

    Args:
        fy_id: Financial year ID
    """
    r = await ctx.deps.http_client.get(
        f"{ctx.deps.base_url}/reports/cash-flow",
        params={"fy_id": fy_id},
    )
    r.raise_for_status()
    return r.json()


async def _list_accounts(ctx: RunContext[StowDeps]) -> list[dict]:
    """List all accounts with current balances — useful for balance queries."""
    r = await ctx.deps.http_client.get(f"{ctx.deps.base_url}/accounts")
    r.raise_for_status()
    return r.json()


def build_report_agent(model: Any) -> Agent[StowDeps, str]:
    return Agent(
        model=model,
        deps_type=StowDeps,
        instructions=_INSTRUCTIONS,
        tools=[
            _get_financial_years,
            _get_trial_balance,
            _get_profit_loss,
            _get_balance_sheet,
            _get_cash_flow,
            _list_accounts,
        ],
    )
