from __future__ import annotations

from typing import Any

from pydantic_ai import Agent, RunContext

from agent.activity import emit
from agent.deps import StowDeps
from agent.subagents.transaction import _get_active_fy, _list_accounts

_INSTRUCTIONS = """\
You are the investment agent for an Indian personal finance system.
You manage fixed deposits, mutual fund and stock lots, and portfolio queries.

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
Always call get_active_fy to get the fy_id before creating any investment.
Call list_accounts to resolve account names to IDs (bank, trading, investment accounts).
Call list_fds or list_investment_accounts to find existing investment account IDs.

## Queries
Use get_holdings, get_portfolio, get_capital_gains for portfolio reporting.
"""


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
    narration: str,
) -> dict:
    """Open a fixed deposit and record the cash movement in the ledger.

    Args:
        name: FD name/label (e.g. "HDFC FD May 2027")
        principal: Principal amount in paise
        interest_rate: Annual interest rate in basis points (e.g. 750 = 7.50%)
        start_date: ISO date string when FD opens
        maturity_date: ISO date string when FD matures
        compounding: simple | monthly | quarterly | yearly
        from_account_id: Bank/trading account to debit (funds the FD)
        fy_id: Financial year ID
        date: Transaction date (ISO string, usually same as start_date)
        narration: Transaction description
    """
    await emit("Creating fixed deposit")
    r = await ctx.deps.http_client.post(
        f"{ctx.deps.base_url}/investments/fds",
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
            "narration": narration,
        },
    )
    r.raise_for_status()
    return r.json()


async def _mature_fd(
    ctx: RunContext[StowDeps],
    fd_account_id: int,
    to_account_id: int,
    fy_id: int,
    date: str,
    narration: str,
) -> dict:
    """Process FD maturity: receive principal + interest, recognise interest income.

    Args:
        fd_account_id: The FD account ID (from list_fds)
        to_account_id: Bank/trading account that receives the maturity proceeds
        fy_id: Financial year ID
        date: Maturity date (ISO string)
        narration: Transaction description
    """
    await emit("Processing FD maturity")
    r = await ctx.deps.http_client.post(
        f"{ctx.deps.base_url}/investments/fds/{fd_account_id}/mature",
        json={
            "to_account_id": to_account_id,
            "fy_id": fy_id,
            "date": date,
            "narration": narration,
        },
    )
    r.raise_for_status()
    return r.json()


async def _list_fds(ctx: RunContext[StowDeps]) -> list[dict]:
    """List all active fixed deposits with accrued interest."""
    await emit("Fetching fixed deposits")
    r = await ctx.deps.http_client.get(f"{ctx.deps.base_url}/investments/fds")
    r.raise_for_status()
    return r.json()


async def _buy_investment(
    ctx: RunContext[StowDeps],
    account_id: int,
    fy_id: int,
    date: str,
    units: int,
    cost_per_unit: int,
    bank_account_id: int,
    narration: str,
) -> dict:
    """Record a purchase of MF units or stock.
    The INVESTMENT account is debited (its balance increases).
    The PAYING account (bank/trading) is credited (its balance decreases).

    Args:
        account_id: The INVESTMENT account being purchased (equity_mf or stock) — money flows INTO this account
        fy_id: Financial year ID
        date: Purchase date (ISO string)
        units: Units purchased in milliunits (1 unit = 1000 milliunits)
        cost_per_unit: Cost per milliunit in paise (NAV × 1000 ÷ 100)
        bank_account_id: The SOURCE account paying for the purchase (bank or trading account) — money flows OUT of this
        narration: Transaction description
    """
    await emit("Recording purchase")
    r = await ctx.deps.http_client.post(
        f"{ctx.deps.base_url}/investments/{account_id}/buy",
        json={
            "fy_id": fy_id,
            "date": date,
            "units": units,
            "cost_per_unit": cost_per_unit,
            "bank_account_id": bank_account_id,
            "narration": narration,
        },
    )
    r.raise_for_status()
    return r.json()


async def _sell_investment(
    ctx: RunContext[StowDeps],
    account_id: int,
    fy_id: int,
    date: str,
    units: int,
    price_per_unit: int,
    bank_account_id: int,
    narration: str,
) -> list[dict]:
    """Record a sale of MF units or stock (FIFO), credit the receiving account, book capital gains.

    Args:
        account_id: Investment account ID
        fy_id: Financial year ID
        date: Sale date (ISO string)
        units: Units to sell in milliunits
        price_per_unit: Sale price per milliunit in paise
        bank_account_id: Account to credit with proceeds — bank or trading account
        narration: Transaction description
    """
    await emit("Recording sale")
    r = await ctx.deps.http_client.post(
        f"{ctx.deps.base_url}/investments/{account_id}/sell",
        json={
            "fy_id": fy_id,
            "date": date,
            "units": units,
            "price_per_unit": price_per_unit,
            "bank_account_id": bank_account_id,
            "narration": narration,
        },
    )
    r.raise_for_status()
    return r.json()


async def _get_holdings(ctx: RunContext[StowDeps], account_id: int) -> list[dict]:
    """Get current lot holdings for an investment account.

    Args:
        account_id: Investment account ID
    """
    await emit("Fetching holdings")
    r = await ctx.deps.http_client.get(f"{ctx.deps.base_url}/investments/{account_id}/holdings")
    r.raise_for_status()
    return r.json()


async def _get_portfolio(ctx: RunContext[StowDeps], account_id: int) -> list[dict]:
    """Get portfolio with current value and unrealized gains (requires a price quote on file).

    Args:
        account_id: Investment account ID
    """
    await emit("Fetching portfolio")
    r = await ctx.deps.http_client.get(f"{ctx.deps.base_url}/investments/{account_id}/portfolio")
    r.raise_for_status()
    return r.json()


async def _get_capital_gains(
    ctx: RunContext[StowDeps],
    account_id: int,
    fy_id: int,
) -> dict:
    """Get STCG/LTCG capital gains summary for an account in a financial year.

    Args:
        account_id: Investment account ID
        fy_id: Financial year ID
    """
    await emit("Calculating capital gains")
    r = await ctx.deps.http_client.get(
        f"{ctx.deps.base_url}/investments/{account_id}/capital-gains",
        params={"fy_id": fy_id},
    )
    r.raise_for_status()
    return r.json()


async def _list_investment_accounts(ctx: RunContext[StowDeps]) -> list[dict]:
    """List all investment accounts (equity_mf, stock, fd, ppf)."""
    await emit("Fetching investment accounts")
    r = await ctx.deps.http_client.get(f"{ctx.deps.base_url}/accounts")
    r.raise_for_status()
    accounts = r.json()
    return [a for a in accounts if a.get("investment_subtype")]


def build_investment_agent(model: Any) -> Agent[StowDeps, str]:
    return Agent(
        model=model,
        deps_type=StowDeps,
        instructions=_INSTRUCTIONS,
        tools=[
            _get_active_fy,
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
