"""Manual test script for the Stow orchestrator agent.

Usage:
    uv run python scripts/chat.py [--base-url http://localhost:8000]

Prints each tool call and subagent delegation so you can verify routing.
Loads backend/.env automatically so LLM env vars are available on the host.
"""
from __future__ import annotations

import asyncio
import argparse
import os
from pathlib import Path

# Load .env from the backend directory so STOW_LLM_* vars are available
# when running on the host (outside Docker).
_env_path = Path(__file__).parent.parent / ".env"
if _env_path.exists():
    for line in _env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip())

import httpx
from pydantic_ai import Agent
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from subagents_pydantic_ai import SubAgentCapability, SubAgentConfig

from agent.deps import StowDeps
from agent.subagents.account import build_account_agent
from agent.subagents.import_agent import build_import_agent
from agent.subagents.investment import build_investment_agent
from agent.subagents.recurring import build_recurring_agent
from agent.subagents.report import build_report_agent
from agent.subagents.transaction import build_transaction_agent
from agent.orchestrator import _SYSTEM_PROMPT


def _fmt_tool_call(part: ToolCallPart) -> str:
    args = str(part.args)[:120]
    return f"  → tool_call  [{part.tool_name}]  args={args}"


def _fmt_tool_return(part: ToolReturnPart) -> str:
    content = str(part.content)[:120]
    return f"  ← tool_ret   [{part.tool_name}]  {content}"


def _print_trace(messages: list) -> None:
    for msg in messages:
        if isinstance(msg, ModelResponse):
            for part in msg.parts:
                if isinstance(part, ToolCallPart):
                    print(_fmt_tool_call(part))
        elif isinstance(msg, ModelRequest):
            for part in msg.parts:
                if isinstance(part, ToolReturnPart):
                    print(_fmt_tool_return(part))


def _build_model(llm_url: str, llm_model: str, llm_api_key: str):
    return OpenAIChatModel(
        llm_model,
        provider=OpenAIProvider(base_url=llm_url, api_key=llm_api_key or "not-needed"),
    )


def _build_orchestrator(model) -> Agent:
    subagents = [
        SubAgentConfig(name="transaction_agent", description="Creates, queries, updates, and deletes transactions. Parses natural language descriptions.", agent=build_transaction_agent(model)),
        SubAgentConfig(name="account_agent", description="Lists, creates, and archives ledger accounts. Looks up account IDs, names, and balances.", agent=build_account_agent(model)),
        SubAgentConfig(name="import_agent", description="Imports bank statement PDFs, reviews parsed rows, and posts confirmed transactions.", agent=build_import_agent(model)),
        SubAgentConfig(name="report_agent", description="Generates financial reports and answers balance/spending queries.", agent=build_report_agent(model)),
        SubAgentConfig(name="investment_agent", description="Manages FDs, mutual fund and stock lots, and portfolio/capital gains queries.", agent=build_investment_agent(model)),
        SubAgentConfig(name="recurring_agent", description="Processes recurring transaction schedules due today.", agent=build_recurring_agent(model)),
    ]
    return Agent(
        model=model,
        deps_type=StowDeps,
        instructions=_SYSTEM_PROMPT,
        capabilities=[SubAgentCapability(subagents=subagents, default_model=model, include_general_purpose=False, max_nesting_depth=0)],
    )


async def main(base_url: str, llm_url: str, llm_model: str, llm_api_key: str) -> None:
    print(f"Connecting to backend at {base_url} ...")
    async with httpx.AsyncClient(base_url=base_url, timeout=60.0) as client:
        r = await client.get("/health")
        r.raise_for_status()
        print("Backend OK\n")

        model = _build_model(llm_url, llm_model, llm_api_key)
        orchestrator = _build_orchestrator(model)
        deps = StowDeps(base_url=base_url, http_client=client)

        print("Stow agent ready. Type a message, or 'quit' to exit.\n")
        history = []

        while True:
            try:
                text = input("You: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nBye.")
                break

            if not text:
                continue
            if text.lower() in ("quit", "exit", "q"):
                break

            try:
                result = await orchestrator.run(text, deps=deps, message_history=history)
            except Exception as exc:
                print(f"[ERROR] {exc}\n")
                continue

            # Print tool/subagent trace
            new_messages = result.new_messages()
            _print_trace(new_messages)

            print(f"Bot: {result.output}\n")

            # Accumulate history for multi-turn conversation
            history = result.all_messages()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Stow agent chat")
    parser.add_argument("--base-url", default="http://localhost:8000", help="Backend API URL")
    parser.add_argument("--llm-url", default=os.environ.get("STOW_LLM_BASE_URL", "http://localhost:8001/v1"), help="LLM base URL (no normalization applied)")
    parser.add_argument("--llm-model", default=os.environ.get("STOW_LLM_MODEL", "Qwen3.6-35B-A3B-MLX-VL-oQ4-FP16"), help="LLM model name")
    parser.add_argument("--llm-api-key", default=os.environ.get("STOW_LLM_API_KEY", "omlx"), help="LLM API key")
    args = parser.parse_args()
    asyncio.run(main(args.base_url, args.llm_url, args.llm_model, args.llm_api_key))
