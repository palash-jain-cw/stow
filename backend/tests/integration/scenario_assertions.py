"""Generic assertion helpers for live agent scenarios — no ledger-specific logic."""
from __future__ import annotations

import logging
from dataclasses import dataclass

from agent_harness import AgentRunResult, output_mentions_amount

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ScenarioExpect:
    """Behavioral expectations after one or more agent turns."""

    description: str = ""
    # Text checks (case-insensitive) on combined output unless final_turn_only.
    contains_any: tuple[str, ...] = ()
    contains_all: tuple[str, ...] = ()
    excludes: tuple[str, ...] = ()
    mentions_amount_rupees: int | None = None
    has_proposal: bool | None = None  # True=required, False=forbidden, None=don't care
    has_question: bool | None = None  # True=must ask, False=must not, None=don't care
    final_turn_only: bool = False  # If multi-turn, only check the last turn's output.


@dataclass
class ScenarioResult:
    scenario_id: str
    turns: list[AgentRunResult]

    @property
    def combined_output(self) -> str:
        return "\n".join(t.output for t in self.turns if t.output)

    @property
    def final_output(self) -> str:
        return self.turns[-1].output if self.turns else ""

    @property
    def final_proposal(self):
        return self.turns[-1].proposal if self.turns else None


def _text_for_expect(result: ScenarioResult, expect: ScenarioExpect) -> str:
    return result.final_output if expect.final_turn_only else result.combined_output


def _has_question(text: str) -> bool:
    return "?" in text


def assert_scenario(result: ScenarioResult, expect: ScenarioExpect) -> None:
    text = _text_for_expect(result, expect)
    lower = text.lower()
    failures: list[str] = []

    for needle in expect.contains_all:
        if needle.lower() not in lower:
            failures.append(f"missing required text: {needle!r}")

    if expect.contains_any and not any(n.lower() in lower for n in expect.contains_any):
        failures.append(f"expected one of: {expect.contains_any!r}")

    for banned in expect.excludes:
        if banned.lower() in lower:
            failures.append(f"forbidden text present: {banned!r}")

    if expect.mentions_amount_rupees is not None:
        if not output_mentions_amount(text, expect.mentions_amount_rupees):
            failures.append(f"expected amount ₹{expect.mentions_amount_rupees:,} in output")

    proposal = result.final_proposal if expect.final_turn_only else any(
        t.proposal for t in result.turns
    )
    if expect.has_proposal is True and not proposal:
        failures.append("expected a PROPOSAL: line but none found")
    if expect.has_proposal is False and proposal:
        failures.append("expected no PROPOSAL: line but one was found")

    questioned = _has_question(result.final_output if expect.final_turn_only else text)
    if expect.has_question is True and not questioned:
        failures.append("expected a clarifying question (?) but none found")
    if expect.has_question is False and questioned:
        failures.append("expected no clarifying question but agent asked one")

    if failures:
        logger.error(
            "Scenario %s failed (%s):\n%s",
            result.scenario_id,
            expect.description or "expectations",
            text[:2000],
        )
        raise AssertionError(
            f"Scenario {result.scenario_id!r}: " + "; ".join(failures)
        )
