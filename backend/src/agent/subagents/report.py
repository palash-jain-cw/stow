from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic_ai import Agent, RunContext

from agent.activity import emit
from agent.deps import StowDeps

_INSTRUCTIONS = """\
You are the report agent for Stow, an Indian personal finance system.
You answer financial queries and generate structured financial reports.

## Query routing
1. **Balance query** ("what's my HDFC balance", "show all accounts", "/balance") →
   call list_accounts; filter by account name; format balance in ₹.
2. **Spending / income query** ("how much did I spend on food this month") →
   call get_current_date first, resolve date range, then call list_transactions with
   from_date / to_date and account_id or narration_q filters; aggregate the amounts.
3. **Structured report** ("show P&L", "trial balance", "balance sheet", "cash flow") →
   call get_financial_years to get fy_id, then call the relevant report tool.

## Date resolution — always call get_current_date first
- "this month"   → YYYY-MM-01 … today
- "last month"   → first … last day of previous month
- "this FY"      → FY containing today (from get_financial_years start_date/end_date)
- "last FY"      → preceding FY
- "this quarter" → current calendar quarter start … today
- "last quarter" → previous calendar quarter (Jan-Mar | Apr-Jun | Jul-Sep | Oct-Dec)
- "this week"    → Monday of current week … today
- "last week"    → previous Monday … Sunday
- "YTD"          → Jan 1 of current year … today
If no date range is given for a spending query, ask ONE clarifying question before proceeding.

## Formatting
- Amounts: ₹X,XX,XXX.XX (Indian commas; divide paise by 100).
- Dates: DD Mon YYYY (e.g., 16 May 2026).
- Balance: one line per account — name + balance.
- Spending: total prominently, brief transaction list if helpful.
- Structured report: key totals in readable prose, not a raw data dump.
- Keep responses short and actionable.
"""


async def _get_current_date(ctx: RunContext[StowDeps]) -> dict:
    """Return today's date. Call this before resolving any relative date expression."""
    await emit("Checking date")
    now = datetime.now()
    return {
        "date": now.strftime("%Y-%m-%d"),
        "year": now.year,
        "month": now.month,
        "day": now.day,
        "day_name": now.strftime("%A"),
    }


async def _get_financial_years(ctx: RunContext[StowDeps]) -> list[dict]:
    """List all financial years with start_date, end_date, and status."""
    await emit("Fetching financial years")
    r = await ctx.deps.http_client.get(f"{ctx.deps.base_url}/financial-years")
    r.raise_for_status()
    return r.json()


async def _list_accounts(ctx: RunContext[StowDeps]) -> list[dict]:
    """List all accounts with current balances (in paise). Use for balance queries."""
    await emit("Fetching account balances")
    r = await ctx.deps.http_client.get(f"{ctx.deps.base_url}/accounts")
    r.raise_for_status()
    return r.json()


async def _list_transactions(
    ctx: RunContext[StowDeps],
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    account_id: Optional[int] = None,
    narration_q: Optional[str] = None,
    txn_type: Optional[str] = None,
) -> list[dict]:
    """List transactions with optional filters. Use for spending / income queries.

    Args:
        from_date: ISO date string (YYYY-MM-DD), inclusive start of range
        to_date: ISO date string (YYYY-MM-DD), inclusive end of range
        account_id: Filter by account involved in the transaction
        narration_q: Case-insensitive substring match on narration
        txn_type: Filter by type: payment | receipt | journal | contra
    """
    await emit("Searching transactions")
    params: dict[str, Any] = {}
    if from_date:
        params["from_date"] = from_date
    if to_date:
        params["to_date"] = to_date
    if account_id:
        params["account_id"] = account_id
    if narration_q:
        params["q"] = narration_q
    if txn_type:
        params["type"] = txn_type
    r = await ctx.deps.http_client.get(f"{ctx.deps.base_url}/transactions", params=params)
    r.raise_for_status()
    return r.json()


async def _get_trial_balance(ctx: RunContext[StowDeps], fy_id: int) -> dict:
    """Get the trial balance for a financial year.

    Args:
        fy_id: Financial year ID
    """
    await emit("Generating trial balance")
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
    await emit("Generating P&L report")
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
    await emit("Generating balance sheet")
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
    await emit("Generating cash flow statement")
    r = await ctx.deps.http_client.get(
        f"{ctx.deps.base_url}/reports/cash-flow",
        params={"fy_id": fy_id},
    )
    r.raise_for_status()
    return r.json()


def build_report_agent(model: Any) -> Agent[StowDeps, str]:
    return Agent(
        model=model,
        deps_type=StowDeps,
        instructions=_INSTRUCTIONS,
        tools=[
            _get_current_date,
            _get_financial_years,
            _list_accounts,
            _list_transactions,
            _get_trial_balance,
            _get_profit_loss,
            _get_balance_sheet,
            _get_cash_flow,
        ],
    )
