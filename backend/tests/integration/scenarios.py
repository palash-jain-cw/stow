"""Catalog of live LLM agent scenarios.

Test DB fixtures (finance_setup) provide generic sample accounts — scenarios describe
user behavior and expected agent *behavior*, not hard-coded production ledger names.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from scenario_assertions import ScenarioExpect

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"


class TurnKind(str, Enum):
    TEXT = "text"
    IMAGE = "image"


@dataclass(frozen=True)
class ScenarioTurn:
    kind: TurnKind
    content: str  # user text, or fixture filename for IMAGE


@dataclass(frozen=True)
class AgentScenario:
    id: str
    category: str
    description: str
    turns: tuple[ScenarioTurn, ...]
    expect: ScenarioExpect
    requires_finance_setup: bool = True
    max_tokens: int = 1024


def _text(content: str) -> ScenarioTurn:
    return ScenarioTurn(TurnKind.TEXT, content)


def _image(filename: str) -> ScenarioTurn:
    return ScenarioTurn(TurnKind.IMAGE, filename)


# ─── Scenario catalog ───────────────────────────────────────────────────────
# Add new scenarios here. Keep expectations behavioral, not account-specific.

SCENARIOS: tuple[AgentScenario, ...] = (
    AgentScenario(
        id="nl-payment-clear",
        category="payment",
        description="Clear NL payment with both accounts named → proposal or confirm path",
        turns=(_text("pay ₹500 from HDFC Savings to Food & Dining for lunch today"),),
        expect=ScenarioExpect(
            description="mentions amount and moves toward recording",
            mentions_amount_rupees=500,
            contains_any=("confirm", "proposal", "payment", "food", "lunch"),
        ),
        max_tokens=1024,
    ),
    AgentScenario(
        id="nl-payment-ambiguous",
        category="payment",
        description="Missing source account → agent should clarify",
        turns=(_text("spent ₹500 on swiggy yesterday"),),
        expect=ScenarioExpect(
            description="asks which account or otherwise clarifies",
            mentions_amount_rupees=500,
            contains_any=("which account", "account", "paid from", "swiggy"),
            has_question=True,
            has_proposal=False,
        ),
    ),
    AgentScenario(
        id="balance-query",
        category="query",
        description="Balance question → report path, not a transaction proposal",
        turns=(_text("What is my HDFC Savings balance?"),),
        expect=ScenarioExpect(
            description="answers balance without posting a transaction",
            contains_any=("balance", "hdfc", "₹"),
            has_proposal=False,
            has_question=False,
        ),
    ),
    AgentScenario(
        id="report-trial-balance",
        category="query",
        description="Financial report request → report agent, not payment",
        turns=(_text("Show me the trial balance"),),
        expect=ScenarioExpect(
            description="report-oriented response",
            contains_any=("trial", "balance", "account", "debit", "credit", "report"),
            has_proposal=False,
        ),
    ),
    AgentScenario(
        id="investment-buy-mf",
        category="routing",
        description="MF purchase → investment routing, not a simple expense payment",
        turns=(_text("Buy ₹5000 of Parag Parikh Flexi Cap mutual fund from HDFC Savings"),),
        expect=ScenarioExpect(
            description="investment-related handling",
            contains_any=("invest", "mutual fund", "mf", "fund", "portfolio", "units", "nav"),
            excludes=("food & dining",),
            has_proposal=False,
        ),
        max_tokens=1024,
    ),
    AgentScenario(
        id="help-command",
        category="meta",
        description="/help explains capabilities",
        turns=(_text("/help"),),
        expect=ScenarioExpect(
            description="lists what Stow can do",
            contains_any=("help", "transaction", "balance", "import", "recurring", "invest"),
            has_proposal=False,
        ),
        requires_finance_setup=False,
    ),
    AgentScenario(
        id="greeting",
        category="meta",
        description="Casual greeting → friendly response, no error",
        turns=(_text("Hi"),),
        expect=ScenarioExpect(
            description="responds without crashing",
            contains_any=("hi", "hello", "help", "stow", "finance", "assist"),
            has_proposal=False,
        ),
        requires_finance_setup=False,
    ),
    AgentScenario(
        id="vision-upi-extract",
        category="vision",
        description="UPI screenshot turn 1 → extract details; question OK if source ambiguous",
        turns=(_image("WhatsApp Image 2026-05-18 at 1.37.50 PM.jpeg"),),
        expect=ScenarioExpect(
            description="extracts amount and payee from image",
            mentions_amount_rupees=4900,
            contains_any=("pankhuri", "jain"),
        ),
        max_tokens=1024,
    ),
    AgentScenario(
        id="vision-upi-multi-turn",
        category="vision",
        description="Screenshot then user names source account → progress toward proposal",
        turns=(
            _image("WhatsApp Image 2026-05-18 at 1.37.50 PM.jpeg"),
            _text("HDFC Savings"),  # generic test-ledger name; simulates user answering
        ),
        expect=ScenarioExpect(
            description="after account clarification, moves forward",
            mentions_amount_rupees=4900,
            contains_any=("confirm", "proposal", "payment", "pankhuri", "4900"),
            final_turn_only=True,
            has_question=False,
        ),
        max_tokens=1024,
    ),
    AgentScenario(
        id="nl-receipt",
        category="payment",
        description="Salary receipt → receipt/income handling",
        turns=(_text("Received salary ₹50000 in HDFC Savings today"),),
        expect=ScenarioExpect(
            description="treats as money in, not an expense payment",
            mentions_amount_rupees=50000,
            contains_any=("salary", "receipt", "received", "income", "confirm", "proposal"),
        ),
        max_tokens=1024,
    ),
    AgentScenario(
        id="off-topic-graceful",
        category="meta",
        description="Non-finance question → polite deflection",
        turns=(_text("What's the weather in Mumbai?"),),
        expect=ScenarioExpect(
            description="does not hallucinate a transaction",
            has_proposal=False,
            contains_any=("finance", "transaction", "account", "can't", "cannot", "help", "stow"),
        ),
        requires_finance_setup=False,
    ),
)

SCENARIO_BY_ID: dict[str, AgentScenario] = {s.id: s for s in SCENARIOS}


def scenarios_by_category(category: str | None = None) -> tuple[AgentScenario, ...]:
    if category is None:
        return SCENARIOS
    return tuple(s for s in SCENARIOS if s.category == category)


def scenario_ids() -> list[str]:
    return [s.id for s in SCENARIOS]
