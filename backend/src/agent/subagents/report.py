from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic_ai import Agent, RunContext

from agent.activity import emit
from agent.deps import StowDeps
from agent.tool_errors import stow_get, tool_safe

_INSTRUCTIONS = """\
You are the report agent for Stow, an Indian personal finance system.
You answer financial queries and generate structured financial reports.

When any tool returns a string starting with "Error:", read the message, fix the issue,
retry, or ask the user one clarifying question.

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


@tool_safe("get_current_date")
async def _get_current_date(ctx: RunContext[StowDeps]) -> dict | str:
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


@tool_safe("get_financial_years")
async def _get_financial_years(ctx: RunContext[StowDeps]) -> list[dict] | str:
    """List all financial years with start_date, end_date, and status."""
    await emit("Fetching financial years")
    return await stow_get(ctx.deps, "/financial-years", tool_name="get_financial_years")


@tool_safe("list_accounts")
async def _list_accounts(ctx: RunContext[StowDeps]) -> list[dict] | str:
    """List all accounts with current balances (in paise). Use for balance queries."""
    await emit("Fetching account balances")
    return await stow_get(ctx.deps, "/accounts", tool_name="list_accounts")


@tool_safe("list_transactions")
async def _list_transactions(
    ctx: RunContext[StowDeps],
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    account_id: Optional[int] = None,
    narration_q: Optional[str] = None,
    txn_type: Optional[str] = None,
) -> list[dict] | str:
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
    return await stow_get(ctx.deps, "/transactions", tool_name="list_transactions", params=params)


@tool_safe("get_trial_balance")
async def _get_trial_balance(ctx: RunContext[StowDeps], fy_id: int) -> dict | str:
    """Get the trial balance for a financial year.

    Args:
        fy_id: Financial year ID
    """
    await emit("Generating trial balance")
    return await stow_get(
        ctx.deps,
        "/reports/trial-balance",
        tool_name="get_trial_balance",
        params={"fy_id": fy_id},
    )


@tool_safe("get_profit_loss")
async def _get_profit_loss(ctx: RunContext[StowDeps], fy_id: int) -> dict | str:
    """Get the profit & loss report for a financial year.

    Args:
        fy_id: Financial year ID
    """
    await emit("Generating P&L report")
    return await stow_get(
        ctx.deps,
        "/reports/profit-loss",
        tool_name="get_profit_loss",
        params={"fy_id": fy_id},
    )


@tool_safe("get_balance_sheet")
async def _get_balance_sheet(ctx: RunContext[StowDeps], fy_id: int) -> dict | str:
    """Get the balance sheet for a financial year.

    Args:
        fy_id: Financial year ID
    """
    await emit("Generating balance sheet")
    return await stow_get(
        ctx.deps,
        "/reports/balance-sheet",
        tool_name="get_balance_sheet",
        params={"fy_id": fy_id},
    )


@tool_safe("get_cash_flow")
async def _get_cash_flow(ctx: RunContext[StowDeps], fy_id: int) -> dict | str:
    """Get the cash flow statement for a financial year.

    Args:
        fy_id: Financial year ID
    """
    await emit("Generating cash flow statement")
    return await stow_get(
        ctx.deps,
        "/reports/cash-flow",
        tool_name="get_cash_flow",
        params={"fy_id": fy_id},
    )


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
