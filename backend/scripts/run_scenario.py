#!/usr/bin/env python3
"""Run live agent scenarios from the catalog against a running Stow backend.

Usage:
    uv run python scripts/run_scenario.py --list
    uv run python scripts/run_scenario.py --scenario nl-payment-clear
    uv run python scripts/run_scenario.py --scenario vision-upi-extract
    uv run python scripts/run_scenario.py "custom one-off prompt"

Requires backend at http://localhost:8000 and STOW_LLM_* in .env.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests" / "integration"))

from tests.load_env import load_llm_env

load_llm_env()

import httpx

from agent.deps import StowDeps
from scenario_assertions import assert_scenario
from scenario_runner import run_agent_scenario
from scenarios import SCENARIO_BY_ID, SCENARIOS

logger = logging.getLogger(__name__)


def _print_list() -> None:
    print("Available scenarios:\n")
    for s in SCENARIOS:
        turns = " → ".join(
            t.content[:40] + ("…" if len(t.content) > 40 else "")
            if t.kind.value == "text"
            else f"[image:{t.content}]"
            for t in s.turns
        )
        print(f"  {s.id:<28} [{s.category}]  {s.description}")
        print(f"    turns: {turns}\n")


async def _run_catalog_scenario(scenario_id: str, base_url: str, check: bool) -> int:
    scenario = SCENARIO_BY_ID.get(scenario_id)
    if scenario is None:
        logger.error("Unknown scenario %r. Use --list.", scenario_id)
        return 1

    async with httpx.AsyncClient(base_url=base_url, timeout=180.0) as client:
        try:
            await client.get("/health")
        except Exception:
            logger.error("Backend not reachable: %s", traceback.format_exc())
            return 1

        deps = StowDeps(base_url=base_url, http_client=client)
        print(f"\n=== Scenario: {scenario.id} ===")
        print(scenario.description)
        try:
            result = await run_agent_scenario(scenario, deps)
        except Exception:
            logger.error("Run failed: %s", traceback.format_exc())
            return 1

        for i, turn in enumerate(result.turns, 1):
            print(f"\n--- Turn {i} ---")
            print(turn.output)
            if turn.proposal:
                print("\n--- Proposal ---")
                print(turn.proposal)

        if check:
            try:
                assert_scenario(result, scenario.expect)
                print("\n✓ Expectations met")
            except AssertionError as exc:
                print(f"\n✗ Expectations failed: {exc}")
                return 1
        return 0


async def _run_adhoc(text: str, base_url: str) -> int:
    from agent.orchestrator import build_orchestrator
    from agent.transport.proposal import parse_proposal
    from stow.ai_config import model_settings

    async with httpx.AsyncClient(base_url=base_url, timeout=180.0) as client:
        await client.get("/health")
        orchestrator = build_orchestrator()
        deps = StowDeps(base_url=base_url, http_client=client)
        result = await orchestrator.run(text, deps=deps, model_settings=model_settings("orchestrator"))
        output = str(result.output).strip()
        proposal, _ = parse_proposal(output)
        print(output)
        if proposal:
            print("\n--- Proposal ---")
            print(proposal)
        return 0


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Run Stow agent scenarios")
    parser.add_argument("text", nargs="?", help="Ad-hoc prompt (instead of --scenario)")
    parser.add_argument("--scenario", "-s", help="Scenario id from catalog (see --list)")
    parser.add_argument("--list", "-l", action="store_true", help="List scenario catalog")
    parser.add_argument("--no-check", action="store_true", help="Skip expectation checks")
    parser.add_argument("--base-url", default="http://localhost:8000")
    args = parser.parse_args()

    if args.list:
        _print_list()
        return 0
    if args.scenario:
        return asyncio.run(_run_catalog_scenario(args.scenario, args.base_url, not args.no_check))
    if args.text:
        return asyncio.run(_run_adhoc(args.text, args.base_url))
    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
