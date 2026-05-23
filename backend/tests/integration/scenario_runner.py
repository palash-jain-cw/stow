"""Execute scenario catalog turns against the orchestrator."""
from __future__ import annotations

import logging
import traceback
from pathlib import Path

from agent.deps import StowDeps
from agent_harness import AgentRunResult, image_prompt, mime_for_path, run_orchestrator
from scenario_assertions import ScenarioResult
from scenarios import FIXTURES_DIR, AgentScenario, ScenarioTurn, TurnKind

logger = logging.getLogger(__name__)


def _turn_prompt(turn: ScenarioTurn) -> str | list:
    if turn.kind == TurnKind.TEXT:
        return turn.content
    path = FIXTURES_DIR / turn.content
    if not path.exists():
        raise FileNotFoundError(f"Scenario fixture image not found: {path}")
    return image_prompt(path.read_bytes(), mime_type=mime_for_path(path.name))


async def run_agent_scenario(scenario: AgentScenario, deps: StowDeps) -> ScenarioResult:
    history = []
    results: list[AgentRunResult] = []
    try:
        for i, turn in enumerate(scenario.turns):
            prompt = _turn_prompt(turn)
            logger.info("Scenario %s turn %d/%d", scenario.id, i + 1, len(scenario.turns))
            result = await run_orchestrator(
                prompt,
                deps,
                message_history=history,
                max_tokens=scenario.max_tokens,
            )
            results.append(result)
            history = result.messages
    except Exception:
        logger.error("Scenario %s failed: %s", scenario.id, traceback.format_exc())
        raise
    return ScenarioResult(scenario_id=scenario.id, turns=results)
