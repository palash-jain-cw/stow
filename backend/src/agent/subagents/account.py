from __future__ import annotations

from typing import Any, Optional

from pydantic_ai import Agent, RunContext

from agent.activity import emit
from agent.deps import StowDeps
from agent.tool_errors import stow_get, stow_post, tool_safe

_INSTRUCTIONS = """\
You are the account agent for an Indian personal finance system.
You look up, create, and archive accounts in the double-entry ledger.

Account natures: asset | liability | equity | income | expense
Investment subtypes: equity_mf | stock | fd | ppf

When any tool returns a string starting with "Error:", read the message, fix the issue,
retry, or ask the user one clarifying question.

Always list accounts first to confirm names/IDs before operating on them.
"""


@tool_safe("list_accounts")
async def _list_accounts(ctx: RunContext[StowDeps], include_archived: bool = False) -> list[dict] | str:
    """List all accounts with their current balances and group info.

    Args:
        include_archived: Whether to include archived accounts (default False)
    """
    await emit("Fetching accounts")
    return await stow_get(
        ctx.deps,
        "/accounts",
        tool_name="list_accounts",
        params={"include_archived": include_archived},
    )


@tool_safe("get_account")
async def _get_account(ctx: RunContext[StowDeps], account_id: int) -> dict | str:
    """Get a single account with its current balance.

    Args:
        account_id: Account ID
    """
    await emit("Fetching account")
    return await stow_get(ctx.deps, f"/accounts/{account_id}", tool_name="get_account")


@tool_safe("create_account")
async def _create_account(
    ctx: RunContext[StowDeps],
    name: str,
    group_id: int,
    investment_subtype: Optional[str] = None,
    currency: str = "INR",
) -> dict | str:
    """Create a new account in the ledger.

    Args:
        name: Account name
        group_id: Account group ID (determines nature)
        investment_subtype: equity_mf | stock | fd | ppf (for investment accounts)
        currency: Currency code, default INR
    """
    await emit("Creating account")
    body: dict[str, Any] = {"name": name, "group_id": group_id, "currency": currency}
    if investment_subtype:
        body["investment_subtype"] = investment_subtype
    return await stow_post(ctx.deps, "/accounts", tool_name="create_account", json=body)


@tool_safe("archive_account")
async def _archive_account(ctx: RunContext[StowDeps], account_id: int) -> dict | str:
    """Soft-delete (archive) an account. It will no longer appear in default listings.

    Args:
        account_id: Account ID to archive
    """
    await emit("Archiving account")
    return await stow_post(ctx.deps, f"/accounts/{account_id}/archive", tool_name="archive_account")


@tool_safe("get_account_ledger")
async def _get_account_ledger(ctx: RunContext[StowDeps], account_id: int) -> list[dict] | str:
    """Get the full transaction ledger for an account.

    Args:
        account_id: Account ID
    """
    await emit("Fetching account ledger")
    return await stow_get(ctx.deps, f"/accounts/{account_id}/ledger", tool_name="get_account_ledger")


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
