from __future__ import annotations

from typing import Any, Optional

from pydantic_ai import Agent, RunContext

from agent.activity import emit
from agent.deps import StowDeps
from agent.subagents.transaction import _get_active_fy, _get_fy_for_date, _list_accounts
from agent.tool_errors import is_tool_error, stow_get, stow_post, tool_safe

_INSTRUCTIONS = """\
You are the investment agent for an Indian personal finance system.
You manage fixed deposits, mutual fund and stock lots, and portfolio queries.

When any tool returns a string starting with "Error:", read the message, fix the issue,
retry, or ask the user one clarifying question.

Key facts:
- All amounts in paise (1 INR = 100 paise)
- Units are in milliunits (1 unit = 1000 milliunits; pass actual_units × 1000)
- cost_per_unit = NAV/price in paise per unit (NOT per milliunit): NAV_rupees × 100  (e.g. ₹810.45 → 81045)
- Formula: total_cost_paise = units_milliunits × cost_per_unit / 1000
- Interest rates are in basis points (750 bps = 7.50% p.a.)
- Capital gains: STCG (short-term) | LTCG (long-term)
- Lot disposal follows FIFO order

## Creating investments — always needs a paying account and FY
Every investment creates a balanced double-entry transaction automatically.
You must always obtain:
  - The account to pay FROM (bank account or trading account like Zerodha)
  - The active financial year ID (call list_fds or list_investment_accounts to find IDs;
    call the orchestrator's get_active_fy if you need the FY)

### Open a Fixed Deposit
Use create_fd. Required: name, principal (paise), interest_rate (bps), start_date,
maturity_date, compounding, from_account_id, fy_id, date, narration.
This creates the FD account, FD metadata, and the paired transaction in one call.

### Buy MF units or stocks
Use buy_investment.
- account_id = the INVESTMENT account (e.g. "Parag Parikh Flexi Cap") — money goes INTO this account (debited)
- bank_account_id = the PAYING account (e.g. "HDFC Savings") — money comes OUT of this account (credited)
- units: actual_units × 1000  (e.g. 12.345 units → 12345)
- cost_per_unit: NAV_rupees × 100  (e.g. NAV ₹810.45 → 81045)
This creates the lot record and the paired transaction in one call.

### Sell MF units or stocks
Use sell_investment. Required: account_id, fy_id, date, units (milliunits),
price_per_unit (paise/milliunit), bank_account_id (receives the proceeds), narration.
Capital gains entries and the transaction are created automatically.

### Mature a Fixed Deposit
Use mature_fd. Required: fd_account_id, to_account_id (bank that receives proceeds),
fy_id, date, narration.
Principal + accrued interest are credited to to_account; interest income is recognised.

## Queries
## Resolving accounts and FY before every operation
Use get_fy_for_date with the transaction date to resolve fy_id (or omit fy_id; the server resolves from date).
Call list_accounts to resolve account names to IDs (bank, trading, investment accounts).
Call list_fds or list_investment_accounts to find existing investment account IDs.

## Queries
Use get_holdings, get_portfolio, get_capital_gains for portfolio reporting.
"""


@tool_safe("create_fd")
async def _create_fd(
    ctx: RunContext[StowDeps],
    name: str,
    principal: int,
    interest_rate: int,
    start_date: str,
    maturity_date: str,
    compounding: str,
    from_account_id: int,
    fy_id: int,
    date: str,
    narration: Optional[str] = "",
) -> dict | str:
    """Open a fixed deposit and record the cash movement in the ledger."""
    await emit("Creating fixed deposit")
    return await stow_post(
        ctx.deps,
        "/investments/fds",
        tool_name="create_fd",
        json={
            "name": name,
            "principal": principal,
            "interest_rate": interest_rate,
            "start_date": start_date,
            "maturity_date": maturity_date,
            "compounding": compounding,
            "from_account_id": from_account_id,
            "fy_id": fy_id,
            "date": date,
            "narration": narration or "",
        },
    )


@tool_safe("mature_fd")
async def _mature_fd(
    ctx: RunContext[StowDeps],
    fd_account_id: int,
    to_account_id: int,
    fy_id: int,
    date: str,
    narration: Optional[str] = "",
) -> dict | str:
    """Process FD maturity: receive principal + interest, recognise interest income."""
    await emit("Processing FD maturity")
    return await stow_post(
        ctx.deps,
        f"/investments/fds/{fd_account_id}/mature",
        tool_name="mature_fd",
        json={
            "to_account_id": to_account_id,
            "fy_id": fy_id,
            "date": date,
            "narration": narration or "",
        },
    )


@tool_safe("list_fds")
async def _list_fds(ctx: RunContext[StowDeps]) -> list[dict] | str:
    """List all active fixed deposits with accrued interest."""
    await emit("Fetching fixed deposits")
    return await stow_get(ctx.deps, "/investments/fds", tool_name="list_fds")


@tool_safe("buy_investment")
async def _buy_investment(
    ctx: RunContext[StowDeps],
    account_id: int,
    fy_id: int,
    date: str,
    units: int,
    cost_per_unit: int,
    bank_account_id: int,
    narration: Optional[str] = "",
) -> dict | str:
    """Record a purchase of MF units or stock."""
    await emit("Recording purchase")
    return await stow_post(
        ctx.deps,
        f"/investments/{account_id}/buy",
        tool_name="buy_investment",
        json={
            "fy_id": fy_id,
            "date": date,
            "units": units,
            "cost_per_unit": cost_per_unit,
            "bank_account_id": bank_account_id,
            "narration": narration or "",
        },
    )


@tool_safe("sell_investment")
async def _sell_investment(
    ctx: RunContext[StowDeps],
    account_id: int,
    fy_id: int,
    date: str,
    units: int,
    price_per_unit: int,
    bank_account_id: int,
    narration: Optional[str] = "",
) -> list[dict] | str:
    """Record a sale of MF units or stock (FIFO), credit the receiving account, book capital gains."""
    await emit("Recording sale")
    return await stow_post(
        ctx.deps,
        f"/investments/{account_id}/sell",
        tool_name="sell_investment",
        json={
            "fy_id": fy_id,
            "date": date,
            "units": units,
            "price_per_unit": price_per_unit,
            "bank_account_id": bank_account_id,
            "narration": narration or "",
        },
    )


@tool_safe("get_holdings")
async def _get_holdings(ctx: RunContext[StowDeps], account_id: int) -> list[dict] | str:
    """Get current lot holdings for an investment account."""
    await emit("Fetching holdings")
    return await stow_get(
        ctx.deps,
        f"/investments/{account_id}/holdings",
        tool_name="get_holdings",
    )


@tool_safe("get_portfolio")
async def _get_portfolio(ctx: RunContext[StowDeps], account_id: int) -> list[dict] | str:
    """Get portfolio with current value and unrealized gains (requires a price quote on file)."""
    await emit("Fetching portfolio")
    return await stow_get(
        ctx.deps,
        f"/investments/{account_id}/portfolio",
        tool_name="get_portfolio",
    )


@tool_safe("get_capital_gains")
async def _get_capital_gains(
    ctx: RunContext[StowDeps],
    account_id: int,
    fy_id: int,
) -> dict | str:
    """Get STCG/LTCG capital gains summary for an account in a financial year."""
    await emit("Calculating capital gains")
    return await stow_get(
        ctx.deps,
        f"/investments/{account_id}/capital-gains",
        tool_name="get_capital_gains",
        params={"fy_id": fy_id},
    )


@tool_safe("list_investment_accounts")
async def _list_investment_accounts(ctx: RunContext[StowDeps]) -> list[dict] | str:
    """List all investment accounts (equity_mf, stock, fd, ppf)."""
    await emit("Fetching investment accounts")
    accounts = await stow_get(ctx.deps, "/accounts", tool_name="list_investment_accounts")
    if is_tool_error(accounts):
        return accounts
    return [a for a in accounts if a.get("investment_subtype")]


def build_investment_agent(model: Any) -> Agent[StowDeps, str]:
    return Agent(
        model=model,
        deps_type=StowDeps,
        instructions=_INSTRUCTIONS,
        tools=[
            _get_active_fy,
            _get_fy_for_date,
            _list_accounts,
            _create_fd,
            _mature_fd,
            _list_fds,
            _buy_investment,
            _sell_investment,
            _get_holdings,
            _get_portfolio,
            _get_capital_gains,
            _list_investment_accounts,
        ],
    )
