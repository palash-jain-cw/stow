from __future__ import annotations

from typing import Any

from pydantic_ai import Agent, RunContext

from agent.deps import StowDeps

_INSTRUCTIONS = """\
You are the investment agent for an Indian personal finance system.
You manage fixed deposits, mutual fund and stock lots, and portfolio queries.

Key facts:
- All amounts in paise (1 INR = 100 paise)
- Units are in milliunits (1 unit = 1000 milliunits)
- Cost per unit is paise per milliunit
- Interest rates are in basis points (750 bps = 7.50% p.a.)
- Capital gains: STCG (short-term) | LTCG (long-term)
- Lot disposal follows FIFO order

Use list_fds or list_investment_accounts to find account IDs before operating.
"""


async def _create_fd(
    ctx: RunContext[StowDeps],
    name: str,
    principal: int,
    interest_rate: int,
    start_date: str,
    maturity_date: str,
    compounding: str,
) -> dict:
    """Create a new fixed deposit.

    Args:
        name: FD name/label
        principal: Principal amount in paise
        interest_rate: Annual interest rate in basis points (e.g. 750 = 7.50%)
        start_date: ISO date string
        maturity_date: ISO date string
        compounding: simple | monthly | quarterly | yearly
    """
    r = await ctx.deps.http_client.post(
        f"{ctx.deps.base_url}/investments/fds",
        json={
            "name": name,
            "principal": principal,
            "interest_rate": interest_rate,
            "start_date": start_date,
            "maturity_date": maturity_date,
            "compounding": compounding,
        },
    )
    r.raise_for_status()
    return r.json()


async def _list_fds(ctx: RunContext[StowDeps]) -> list[dict]:
    """List all active fixed deposits with accrued interest."""
    r = await ctx.deps.http_client.get(f"{ctx.deps.base_url}/investments/fds")
    r.raise_for_status()
    return r.json()


async def _buy_investment(
    ctx: RunContext[StowDeps],
    account_id: int,
    transaction_id: int,
    units: int,
    cost_per_unit: int,
    acquisition_date: str,
) -> dict:
    """Record a purchase lot for a mutual fund or stock.

    Args:
        account_id: Investment account ID
        transaction_id: Linked transaction ID
        units: Units purchased in milliunits
        cost_per_unit: Cost per milliunit in paise
        acquisition_date: ISO date string
    """
    r = await ctx.deps.http_client.post(
        f"{ctx.deps.base_url}/investments/{account_id}/buy",
        json={
            "transaction_id": transaction_id,
            "units": units,
            "cost_per_unit": cost_per_unit,
            "acquisition_date": acquisition_date,
        },
    )
    r.raise_for_status()
    return r.json()


async def _sell_investment(
    ctx: RunContext[StowDeps],
    account_id: int,
    transaction_id: int,
    units: int,
    sale_date: str,
    sale_price_per_unit: int,
) -> list[dict]:
    """Record a sale of investment lots (FIFO disposal).

    Args:
        account_id: Investment account ID
        transaction_id: Linked transaction ID
        units: Units sold in milliunits
        sale_date: ISO date string
        sale_price_per_unit: Sale price per milliunit in paise
    """
    r = await ctx.deps.http_client.post(
        f"{ctx.deps.base_url}/investments/{account_id}/sell",
        json={
            "transaction_id": transaction_id,
            "units": units,
            "sale_date": sale_date,
            "sale_price_per_unit": sale_price_per_unit,
        },
    )
    r.raise_for_status()
    return r.json()


async def _get_holdings(ctx: RunContext[StowDeps], account_id: int) -> list[dict]:
    """Get current lot holdings for an investment account.

    Args:
        account_id: Investment account ID
    """
    r = await ctx.deps.http_client.get(f"{ctx.deps.base_url}/investments/{account_id}/holdings")
    r.raise_for_status()
    return r.json()


async def _get_portfolio(ctx: RunContext[StowDeps], account_id: int) -> list[dict]:
    """Get portfolio with current value and unrealized gains (requires a price quote on file).

    Args:
        account_id: Investment account ID
    """
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
    r = await ctx.deps.http_client.get(
        f"{ctx.deps.base_url}/investments/{account_id}/capital-gains",
        params={"fy_id": fy_id},
    )
    r.raise_for_status()
    return r.json()


async def _list_investment_accounts(ctx: RunContext[StowDeps]) -> list[dict]:
    """List all investment accounts (equity_mf, stock, fd, ppf)."""
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
            _create_fd,
            _list_fds,
            _buy_investment,
            _sell_investment,
            _get_holdings,
            _get_portfolio,
            _get_capital_gains,
            _list_investment_accounts,
        ],
    )
