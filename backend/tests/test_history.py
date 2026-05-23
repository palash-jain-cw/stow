from __future__ import annotations

import pytest
from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart

from agent.history import trim_message_history


def _msg(text: str) -> ModelResponse:
    return ModelResponse(parts=[TextPart(text)])


def _req(text: str) -> ModelRequest:
    return ModelRequest(parts=[TextPart(text)])


def test_trim_message_history_keeps_tail():
    messages = [_req(f"u{i}") if i % 2 == 0 else _msg(f"a{i}") for i in range(10)]
    trimmed = trim_message_history(messages, limit=4)
    assert len(trimmed) == 4
    assert trimmed[0] == messages[-4]


def test_trim_message_history_noop_when_short():
    messages = [_req("hi"), _msg("hello")]
    assert trim_message_history(messages, limit=8) is messages
