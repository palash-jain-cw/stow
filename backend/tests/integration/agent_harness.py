"""Helpers for live LLM agent scenario tests."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

from pydantic_ai import BinaryContent
from pydantic_ai.messages import ModelMessage

from agent.deps import StowDeps
from agent.orchestrator import build_orchestrator
from agent.transport.proposal import parse_proposal
from stow.ai_config import model_settings

logger = logging.getLogger(__name__)


@dataclass
class AgentRunResult:
    output: str
    proposal: dict[str, Any] | None
    display_text: str
    messages: list[ModelMessage]


async def run_orchestrator(
    prompt: str | list[Any],
    deps: StowDeps,
    *,
    message_history: list[ModelMessage] | None = None,
    max_tokens: int | None = None,
) -> AgentRunResult:
    from agent.history import trim_message_history

    orchestrator = build_orchestrator()
    logger.info("Running orchestrator prompt=%r", prompt if isinstance(prompt, str) else "<multimodal>")
    settings = model_settings("orchestrator")
    if max_tokens is not None:
        settings = {**settings, "max_tokens": max_tokens}
    history = trim_message_history(message_history or [])
    result = await orchestrator.run(
        prompt,
        deps=deps,
        message_history=history,
        model_settings=settings,
    )
    output = str(result.output).strip()
    proposal, display = parse_proposal(output)
    logger.info("Orchestrator output (first 500 chars): %s", output[:500])
    return AgentRunResult(
        output=output,
        proposal=proposal,
        display_text=display,
        messages=result.all_messages(),
    )


def image_prompt(image_bytes: bytes, mime_type: str = "image/png") -> list[Any]:
    return [
        "Process this UPI payment screenshot",
        BinaryContent(data=image_bytes, media_type=mime_type),
    ]


def output_mentions_amount(output: str, rupees: int) -> bool:
    """True if output mentions the amount in common Indian formats."""
    patterns = [
        rf"₹\s*{rupees:,}",
        rf"₹\s*{rupees}",
        rf"{rupees * 100}\s*paise",
        rf"{rupees * 100}",
    ]
    text = output.lower()
    return any(re.search(p, text, re.IGNORECASE) for p in patterns)


def output_mentions_payee(output: str, *needles: str) -> bool:
    lower = output.lower()
    return any(n.lower() in lower for n in needles)


def mime_for_path(path: str) -> str:
    suffix = path.rsplit(".", 1)[-1].lower()
    return {
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "png": "image/png",
        "webp": "image/webp",
    }.get(suffix, "application/octet-stream")
