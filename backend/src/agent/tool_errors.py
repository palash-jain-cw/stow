from __future__ import annotations

import functools
import logging
import traceback
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Literal, TypeVar

import httpx

from agent.deps import StowDeps

logger = logging.getLogger(__name__)

T = TypeVar("T")
ToolResult = T | str

ERROR_PREFIX = "Error:"


def is_tool_error(value: Any) -> bool:
    """True when a tool returned an error string for the agent to handle."""
    return isinstance(value, str) and value.startswith(ERROR_PREFIX)


def format_tool_error(tool_name: str, exc: BaseException | str) -> str:
    """Format a tool failure as a string the LLM can read and act on."""
    if isinstance(exc, httpx.HTTPStatusError):
        detail = exc.response.text[:500] if exc.response is not None else str(exc)
        message = f"HTTP {exc.response.status_code}: {detail}"
    else:
        message = str(exc)
    logger.error("Tool %s failed: %s", tool_name, traceback.format_exc())
    return f"{ERROR_PREFIX} {tool_name} failed: {message}"


def tool_safe(name: str | None = None) -> Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[ToolResult[T]]]]:
    """Decorator: catch exceptions in agent tools and return an error string."""

    def decorator(fn: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[ToolResult[T]]]:
        tool_name = name or fn.__name__.lstrip("_")

        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> ToolResult[T]:
            try:
                return await fn(*args, **kwargs)
            except Exception as exc:
                return format_tool_error(tool_name, exc)

        return wrapper

    return decorator


async def stow_get(deps: StowDeps, path: str, *, tool_name: str, **kwargs: Any) -> Any | str:
    """GET JSON from the Stow API; return error string on failure."""
    try:
        response = await deps.http_client.get(f"{deps.base_url}{path}", **kwargs)
        response.raise_for_status()
        return response.json()
    except Exception as exc:
        return format_tool_error(tool_name, exc)


async def stow_post(deps: StowDeps, path: str, *, tool_name: str, **kwargs: Any) -> Any | str:
    """POST to the Stow API; return JSON or error string."""
    try:
        response = await deps.http_client.post(f"{deps.base_url}{path}", **kwargs)
        response.raise_for_status()
        if not response.content:
            return {}
        return response.json()
    except Exception as exc:
        return format_tool_error(tool_name, exc)


async def stow_put(deps: StowDeps, path: str, *, tool_name: str, **kwargs: Any) -> Any | str:
    try:
        response = await deps.http_client.put(f"{deps.base_url}{path}", **kwargs)
        response.raise_for_status()
        return response.json()
    except Exception as exc:
        return format_tool_error(tool_name, exc)


async def stow_delete(deps: StowDeps, path: str, *, tool_name: str, **kwargs: Any) -> Any | str:
    try:
        response = await deps.http_client.delete(f"{deps.base_url}{path}", **kwargs)
        response.raise_for_status()
        if not response.content:
            return {}
        return response.json()
    except Exception as exc:
        return format_tool_error(tool_name, exc)


@dataclass(frozen=True)
class ProposalActionResult:
    """Result of handling a user confirm/decline message."""

    kind: Literal["none", "reply", "agent"]
    message: str = ""
