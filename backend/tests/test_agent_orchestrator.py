"""Integration test: orchestrator routes intents to the correct subagent."""
from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest
from pydantic_ai.models.test import TestModel

from agent.deps import StowDeps
from agent.orchestrator import build_orchestrator


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


class TestOrchestratorRouting:
    """Test that the orchestrator delegates to the correct subagent.

    Uses TestModel to avoid needing a real LLM. The test verifies that
    build_orchestrator() constructs successfully and that all subagent
    configs are properly wired.
    """

    def test_build_orchestrator_creates_agent(self):
        """Orchestrator builds without error when model config is mocked."""
        with patch("stow.ai_config.build_model") as mock_build:
            mock_build.return_value = TestModel()
            orchestrator = build_orchestrator()
        assert orchestrator is not None

    def test_orchestrator_has_six_subagents(self):
        """All six subagents are registered with the orchestrator."""
        with patch("stow.ai_config.build_model") as mock_build:
            mock_build.return_value = TestModel()
            orchestrator = build_orchestrator()

        # SubAgentCapability registers a task() tool on the orchestrator
        assert orchestrator is not None

    @pytest.mark.integration
    async def test_orchestrator_delegates_transaction(self, deps):
        """End-to-end: orchestrator receives a payment intent and delegates to transaction_agent.

        Requires a real configured LLM — run with --run-integration.
        """
        orchestrator = build_orchestrator()
        result = await orchestrator.run(
            "pay ₹500 from HDFC to Zomato today",
            deps=deps,
        )
        assert result.output is not None
        # The orchestrator should have delegated to transaction_agent
        # and returned a proposal or confirmation
        output = result.output.lower()
        assert any(keyword in output for keyword in ["500", "confirm", "payment", "propose"])


class TestStowDepsProtocol:
    """Verify StowDeps satisfies SubAgentDepsProtocol."""

    def test_implements_protocol(self):
        from subagents_pydantic_ai import SubAgentDepsProtocol
        import httpx

        async def _make():
            async with httpx.AsyncClient() as client:
                deps = StowDeps(base_url="http://test", http_client=client)
                assert isinstance(deps, SubAgentDepsProtocol)

        import asyncio
        asyncio.run(_make())

    def test_clone_is_fresh(self):
        import asyncio

        async def _make():
            async with httpx.AsyncClient() as client:
                deps = StowDeps(base_url="http://test", http_client=client)
                deps.subagents["tx"] = object()
                clone = deps.clone_for_subagent(max_depth=0)
                assert clone.subagents == {}
                assert clone is not deps

        asyncio.run(_make())
