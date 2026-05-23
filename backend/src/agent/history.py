from __future__ import annotations

import logging

from pydantic_ai.messages import ModelMessage

logger = logging.getLogger(__name__)

# Keep recent turns only — local models slow down as history grows.
DEFAULT_MAX_HISTORY_MESSAGES = 16


def trim_message_history(
    messages: list[ModelMessage],
    *,
    limit: int = DEFAULT_MAX_HISTORY_MESSAGES,
) -> list[ModelMessage]:
    """Return the tail of conversation history, dropping oldest messages."""
    if len(messages) <= limit:
        return messages
    trimmed = messages[-limit:]
    logger.info(
        "Trimmed message history from %d to %d messages (limit=%d)",
        len(messages),
        len(trimmed),
        limit,
    )
    return trimmed
