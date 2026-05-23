"""Live LLM agent scenario suite.

Run all:
    uv run pytest tests/integration/test_agent_scenarios.py --run-integration -v

Run one category:
    uv run pytest tests/integration/test_agent_scenarios.py --run-integration -v -k payment

Run one scenario by id:
    uv run pytest tests/integration/test_agent_scenarios.py --run-integration -v -k nl-payment-clear

Manual CLI (same catalog):
    uv run python scripts/run_scenario.py --list
    uv run python scripts/run_scenario.py --scenario vision-upi-extract
"""
from __future__ import annotations

import logging

import pytest

from scenario_assertions import assert_scenario
from scenario_runner import run_agent_scenario
from scenarios import SCENARIOS, AgentScenario

logger = logging.getLogger(__name__)

pytestmark = pytest.mark.integration


@pytest.fixture(params=[s.id for s in SCENARIOS], ids=[s.id for s in SCENARIOS])
def scenario_id(request) -> str:
    return request.param


@pytest.fixture
def scenario(scenario_id: str) -> AgentScenario:
    return next(s for s in SCENARIOS if s.id == scenario_id)


class TestAgentScenarios:
    async def test_scenario(self, llm_reachable, agent_deps, finance_setup, scenario: AgentScenario):
        if scenario.requires_finance_setup:
            _ = finance_setup  # ensure FY + sample accounts exist

        result = await run_agent_scenario(scenario, agent_deps)
        for i, turn in enumerate(result.turns):
            logger.info(
                "Scenario %s turn %d output:\n%s",
                scenario.id,
                i + 1,
                turn.output[:1500],
            )
        assert_scenario(result, scenario.expect)
