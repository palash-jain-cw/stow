"""Manual test script for the Stow unified agent.

Usage:
    uv run python scripts/chat.py [--base-url http://localhost:8000]

Prints each tool call so you can verify the agent is using the right tools.
Loads backend/.env automatically so LLM env vars are available on the host.
"""
from __future__ import annotations

import asyncio
import argparse
import os
from pathlib import Path

# Load STOW_LLM_* from repo/backend .env when running on the host (outside Docker).
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from tests.load_env import load_llm_env

load_llm_env()

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

from agent.deps import StowDeps
from agent.agent import build_agent
from stow.ai_config import _model_profile, model_settings


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
    from stow.ai_config import _model_profile

    return OpenAIChatModel(
        llm_model,
        provider=OpenAIProvider(base_url=llm_url, api_key=llm_api_key or "not-needed"),
        profile=_model_profile(llm_model),
        settings=model_settings("agent"),
    )


async def main(base_url: str, llm_url: str, llm_model: str, llm_api_key: str) -> None:
    print(f"Connecting to backend at {base_url} ...")
    async with httpx.AsyncClient(base_url=base_url, timeout=60.0) as client:
        r = await client.get("/health")
        r.raise_for_status()
        print("Backend OK\n")

        model = _build_model(llm_url, llm_model, llm_api_key)
        agent = build_agent()
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
                result = await agent.run(
                    text,
                    deps=deps,
                    message_history=history,
                    model_settings=model_settings("agent"),
                )
            except Exception as exc:
                print(f"[ERROR] {exc}\n")
                continue

            # Print tool call trace
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
