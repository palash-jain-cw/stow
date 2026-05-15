import pytest
from datetime import date as dt_date
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import stow.ai_config as ai_config_module
from stow.main import app
from stow.ai_agent import get_ai_agent, ParsedTransaction


# ---------------------------------------------------------------------------
# Slice 1: GET /ai/config returns env-var values
# ---------------------------------------------------------------------------

def test_get_config_returns_env_vars(client, monkeypatch):
    monkeypatch.setenv("STOW_LLM_BASE_URL", "http://localhost:11434/v1")
    monkeypatch.setenv("STOW_LLM_MODEL", "qwen3:30b")
    monkeypatch.delenv("STOW_LLM_API_KEY", raising=False)
    r = client.get("/ai/config")
    assert r.status_code == 200
    data = r.json()
    assert data["base_url"] == "http://localhost:11434/v1"
    assert data["model"] == "qwen3:30b"


# ---------------------------------------------------------------------------
# Slice 2: POST /ai/config persists to TOML; GET picks it up
# ---------------------------------------------------------------------------

@pytest.fixture()
def isolated_config(tmp_path, monkeypatch):
    """Redirect ~/.stow/config to a temp dir so tests don't touch real config."""
    fake_config = tmp_path / ".stow" / "config"
    monkeypatch.setattr(ai_config_module, "_CONFIG_PATH", fake_config)
    monkeypatch.delenv("STOW_LLM_BASE_URL", raising=False)
    monkeypatch.delenv("STOW_LLM_MODEL", raising=False)
    monkeypatch.delenv("STOW_LLM_API_KEY", raising=False)
    return fake_config


def test_post_config_persists_and_get_reads_it(client, isolated_config):
    r = client.post("/ai/config", json={"base_url": "http://ollama:11434/v1", "model": "llama3"})
    assert r.status_code == 200

    r2 = client.get("/ai/config")
    assert r2.status_code == 200
    data = r2.json()
    assert data["base_url"] == "http://ollama:11434/v1"
    assert data["model"] == "llama3"
    assert isolated_config.exists()


# ---------------------------------------------------------------------------
# Slice 3: POST /ai/test-connection — happy path
# ---------------------------------------------------------------------------

@pytest.fixture()
def mock_agent():
    agent = MagicMock()
    result = MagicMock()
    result.data = "pong"
    agent.run = AsyncMock(return_value=result)
    return agent


def test_test_connection_ok(client, mock_agent, monkeypatch):
    monkeypatch.setenv("STOW_LLM_MODEL", "qwen3:30b")
    app.dependency_overrides[get_ai_agent] = lambda: mock_agent
    try:
        r = client.post("/ai/test-connection")
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert data["model"] == "qwen3:30b"
        assert isinstance(data["latency_ms"], (int, float))
    finally:
        app.dependency_overrides.pop(get_ai_agent, None)


# ---------------------------------------------------------------------------
# Slice 4: POST /ai/test-connection — connection failure
# ---------------------------------------------------------------------------

def test_test_connection_failure(client):
    import httpx
    failing_agent = MagicMock()
    failing_agent.run = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))
    app.dependency_overrides[get_ai_agent] = lambda: failing_agent
    try:
        r = client.post("/ai/test-connection")
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is False
        assert "Connection refused" in data["error"]
        assert data["latency_ms"] is None
    finally:
        app.dependency_overrides.pop(get_ai_agent, None)


# ---------------------------------------------------------------------------
# Slice 5: POST /ai/parse-transaction returns structured ParsedTransaction
# ---------------------------------------------------------------------------

def test_parse_transaction_returns_structured_dict(client, mock_agent):
    parsed = ParsedTransaction(
        type="payment",
        date=dt_date(2026, 5, 10),
        amount=240000,
        narration="Electricity bill",
        from_account_id=1,
        to_account_id=2,
        confidence=0.92,
    )
    result = MagicMock()
    result.data = parsed
    mock_agent.run = AsyncMock(return_value=result)

    app.dependency_overrides[get_ai_agent] = lambda: mock_agent
    try:
        r = client.post(
            "/ai/parse-transaction",
            json={"text": "paid electricity bill 2400 from HDFC last Tuesday"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["type"] == "payment"
        assert data["amount"] == 240000
        assert data["narration"] == "Electricity bill"
        assert data["from_account_id"] == 1
        assert data["to_account_id"] == 2
        assert data["confidence"] == pytest.approx(0.92)
    finally:
        app.dependency_overrides.pop(get_ai_agent, None)


# ---------------------------------------------------------------------------
# Slice 6: Edge cases — prompt includes today's date; amount must be int paise
# ---------------------------------------------------------------------------

def test_parse_transaction_prompt_includes_today(client, mock_agent):
    """Verify that the user prompt sent to the agent contains today's date."""
    from datetime import date as real_date

    parsed = ParsedTransaction(
        type="receipt",
        date=real_date.today(),
        amount=100000,
        narration="Salary",
        from_account_id=3,
        to_account_id=4,
        confidence=0.95,
    )
    result = MagicMock()
    result.data = parsed
    mock_agent.run = AsyncMock(return_value=result)

    app.dependency_overrides[get_ai_agent] = lambda: mock_agent
    try:
        client.post("/ai/parse-transaction", json={"text": "salary received today"})
        call_args = mock_agent.run.call_args
        prompt_text = call_args[0][0]
        assert str(real_date.today()) in prompt_text
    finally:
        app.dependency_overrides.pop(get_ai_agent, None)


def test_parsed_transaction_amount_must_be_int():
    """ParsedTransaction rejects float amounts — amounts are always paise integers."""
    import pydantic
    with pytest.raises(pydantic.ValidationError):
        ParsedTransaction(
            type="payment",
            date=dt_date(2026, 5, 10),
            amount=2400.50,  # non-integer float must be rejected
            narration="test",
            from_account_id=1,
            to_account_id=2,
            confidence=0.9,
        )
