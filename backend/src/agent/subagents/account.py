from __future__ import annotations

from typing import Any, Optional

from pydantic_ai import Agent, RunContext

from agent.deps import StowDeps

_INSTRUCTIONS = """\
You are the account agent for an Indian personal finance system.
You look up, create, and archive accounts in the double-entry ledger.

Account natures: asset | liability | equity | income | expense
Investment subtypes: equity_mf | stock | fd | ppf

Always list accounts first to confirm names/IDs before operating on them.
"""


async def _list_accounts(ctx: RunContext[StowDeps], include_archived: bool = False) -> list[dict]:
    """List all accounts with their current balances and group info.

    Args:
        include_archived: Whether to include archived accounts (default False)
    """
    r = await ctx.deps.http_client.get(
        f"{ctx.deps.base_url}/accounts",
        params={"include_archived": include_archived},
    )
    r.raise_for_status()
    return r.json()


async def _get_account(ctx: RunContext[StowDeps], account_id: int) -> dict:
    """Get a single account with its current balance.

    Args:
        account_id: Account ID
    """
    r = await ctx.deps.http_client.get(f"{ctx.deps.base_url}/accounts/{account_id}")
    r.raise_for_status()
    return r.json()


async def _create_account(
    ctx: RunContext[StowDeps],
    name: str,
    group_id: int,
    investment_subtype: Optional[str] = None,
    currency: str = "INR",
) -> dict:
    """Create a new account in the ledger.

    Args:
        name: Account name
        group_id: Account group ID (determines nature)
        investment_subtype: equity_mf | stock | fd | ppf (for investment accounts)
        currency: Currency code, default INR
    """
    body: dict[str, Any] = {"name": name, "group_id": group_id, "currency": currency}
    if investment_subtype:
        body["investment_subtype"] = investment_subtype
    r = await ctx.deps.http_client.post(f"{ctx.deps.base_url}/accounts", json=body)
    r.raise_for_status()
    return r.json()


async def _archive_account(ctx: RunContext[StowDeps], account_id: int) -> dict:
    """Soft-delete (archive) an account. It will no longer appear in default listings.

    Args:
        account_id: Account ID to archive
    """
    r = await ctx.deps.http_client.post(f"{ctx.deps.base_url}/accounts/{account_id}/archive")
    r.raise_for_status()
    return r.json()


async def _get_account_ledger(ctx: RunContext[StowDeps], account_id: int) -> list[dict]:
    """Get the full transaction ledger for an account.

    Args:
        account_id: Account ID
    """
    r = await ctx.deps.http_client.get(f"{ctx.deps.base_url}/accounts/{account_id}/ledger")
    r.raise_for_status()
    return r.json()


def build_account_agent(model: Any) -> Agent[StowDeps, str]:
    return Agent(
        model=model,
        deps_type=StowDeps,
        instructions=_INSTRUCTIONS,
        tools=[
            _list_accounts,
            _get_account,
            _create_account,
            _archive_account,
            _get_account_ledger,
        ],
    )
