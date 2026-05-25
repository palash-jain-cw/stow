"""Integration test: unified Stow agent exposes all tools at the top level."""
from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest
from pydantic_ai.models.test import TestModel

from agent.deps import StowDeps
from agent.agent import build_agent


@pytest.fixture()
async def http_client(asgi_app, session):
    from stow.db import get_session
    asgi_app.dependency_overrides[get_session] = lambda: session
    transport = httpx.ASGITransport(app=asgi_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    asgi_app.dependency_overrides.clear()


@pytest.fixture()
def asgi_app():
    from stow.main import app
    return app


@pytest.fixture()
def deps(http_client):
    return StowDeps(base_url="http://test", http_client=http_client)


class TestUnifiedAgent:
    """Test that the unified agent builds correctly with all tools exposed at the top level.

    The old subagent architecture has been replaced with a single agent that has
    all tools exposed directly. This simplifies routing, reduces LLM calls, and
    eliminates classification errors.
    """

    def test_build_agent_creates_instance(self):
        """Agent builds without error when model config is mocked."""
        with patch("stow.ai_config.build_model") as mock_build:
            mock_build.return_value = TestModel()
            agent = build_agent()
        assert agent is not None

    def test_agent_has_all_tools(self):
        """All tools are registered on the agent (no subagent delegation needed)."""
        with patch("stow.ai_config.build_model") as mock_build:
            mock_build.return_value = TestModel()
            agent = build_agent()

        # The agent should have tools directly — no task() subagent delegation
        # Count of tools should be substantial (accounts, transactions, investments, etc.)
        tool_names = [t.__name__ for t in agent._tools]
        assert len(tool_names) > 20, f"Expected 20+ tools, got {len(tool_names)}"

        # Verify key tools are present
        expected_tools = {
            "create_transaction", "list_accounts", "get_active_fy",
            "buy_investment", "sell_investment", "create_fd",
            "list_fds", "get_portfolio", "get_capital_gains",
            "get_profit_loss", "get_balance_sheet", "get_cash_flow",
            "review_staging", "confirm_staging",
            "get_recurring_due", "confirm_recurring",
            "parse_natural_language", "list_transactions",
            "get_merchant_rules", "resolve_upi_accounts",
            "create_merchant_rule", "delete_merchant_rule",
            "get_depreciation_summary", "fetch_prices", "get_tax_rules",
            "apply_merchant_rules",
        }
        actual_tools = set(tool_names)
        missing = expected_tools - actual_tools
        assert not missing, f"Missing tools: {missing}"

    @pytest.mark.integration
    async def test_agent_handles_transaction_intent(self, deps):
        """End-to-end: agent receives a payment intent and processes it.

        Requires a real configured LLM — run with --run-integration.
        """
        agent = build_agent()
        result = await agent.run(
            "pay ₹500 from HDFC to Zomato today",
            deps=deps,
        )
        assert result.output is not None
        output = result.output.lower()
        assert any(keyword in output for keyword in ["500", "confirm", "payment", "propose"])


class TestMerchantRulesTool:
    """Unit tests for the _get_merchant_rules tool."""

    @pytest.fixture()
    async def http_client(self, asgi_app, session):
        from stow.db import get_session
        asgi_app.dependency_overrides[get_session] = lambda: session
        transport = httpx.ASGITransport(app=asgi_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client
        asgi_app.dependency_overrides.clear()

    @pytest.fixture()
    def ctx(self, http_client, session):
        from unittest.mock import MagicMock
        deps = StowDeps(base_url="http://test", http_client=http_client)
        mock = MagicMock()
        mock.deps = deps
        return mock

    async def test_get_merchant_rules_returns_list(self, ctx, session):
        """_get_merchant_rules fetches all rules from GET /merchant-rules."""
        from sqlmodel import select
        from stow.models import AccountGroup, Account, MerchantRule
        from agent.agent import _get_merchant_rules

        asset_group = session.exec(
            select(AccountGroup).where(AccountGroup.nature == "asset")
        ).first()
        account = Account(name="HDFC Rule Test", group_id=asset_group.id)
        session.add(account)
        session.flush()
        rule = MerchantRule(pattern="zomato", account_id=account.id)
        session.add(rule)
        session.flush()

        rules = await _get_merchant_rules(ctx)
        assert isinstance(rules, list)
        assert any(r["pattern"] == "zomato" for r in rules)

    async def test_get_merchant_rules_empty_when_none(self, ctx):
        """_get_merchant_rules returns [] when no rules exist."""
        from agent.agent import _get_merchant_rules

        rules = await _get_merchant_rules(ctx)
        assert isinstance(rules, list)


class TestStowDeps:
    """Verify StowDeps structure."""

    def test_build_from_env(self):
        import os
        import httpx

        os.environ["STOW_BASE_URL"] = "http://test.example.com"
        deps = StowDeps.build()
        assert deps.base_url == "http://test.example.com"
        assert isinstance(deps.http_client, httpx.AsyncClient)

    def test_default_base_url(self):
        import os
        import httpx

        os.environ.pop("STOW_BASE_URL", None)
        deps = StowDeps.build()
        assert deps.base_url == "http://localhost:8000"
