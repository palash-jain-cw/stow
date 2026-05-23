from __future__ import annotations

import httpx
import pytest

from agent.tool_errors import format_tool_error, is_tool_error, tool_safe


@tool_safe("demo_tool")
async def _demo_tool(should_fail: bool = False) -> dict | str:
    if should_fail:
        raise RuntimeError("boom")
    return {"ok": True}


@pytest.mark.asyncio
async def test_tool_safe_returns_error_string():
    result = await _demo_tool(should_fail=True)
    assert is_tool_error(result)
    assert "demo_tool failed" in result
    assert "boom" in result


@pytest.mark.asyncio
async def test_tool_safe_returns_success():
    result = await _demo_tool(should_fail=False)
    assert result == {"ok": True}


def test_format_tool_error_http_status():
    request = httpx.Request("POST", "http://localhost/transactions")
    response = httpx.Response(422, request=request, text='{"detail":"bad account"}')
    err = httpx.HTTPStatusError("fail", request=request, response=response)
    message = format_tool_error("create_transaction", err)
    assert message.startswith("Error:")
    assert "422" in message
