import pytest
from datetime import date as dt_date
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import stow.ai_config as ai_config_module
from stow.main import app
from stow.ai_agent import get_ai_agent, ParsedTransaction


def test_qwen_model_profile_merges_system_messages():
    profile = ai_config_module._model_profile("qwen3.6-35b")
    assert profile is not None
    assert profile.openai_chat_supports_multiple_system_messages is False


def test_model_settings_role_caps():
    parse_settings = ai_config_module.model_settings("parse")
    assert parse_settings["max_tokens"] == 512
    assert parse_settings["thinking"] is False

    orch_settings = ai_config_module.model_settings("orchestrator")
    assert orch_settings["max_tokens"] == 1024

    ping_settings = ai_config_module.model_settings("ping")
    assert ping_settings["max_tokens"] == 256

    import_settings = ai_config_module.model_settings("import")
    assert import_settings["max_tokens"] == 65536


def test_build_model_applies_default_settings(monkeypatch):
    monkeypatch.setenv("STOW_LLM_BASE_URL", "http://127.0.0.1:8080/v1")
    monkeypatch.setenv("STOW_LLM_MODEL", "qwen3.6-35b")
    model = ai_config_module.build_model()
    assert model.settings is not None
    assert model.settings.get("max_tokens") == 1024


# ---------------------------------------------------------------------------
# resolve_llm_base_url — host vs Docker
# ---------------------------------------------------------------------------

def test_resolve_llm_base_url_maps_docker_host_on_bare_metal(monkeypatch):
    monkeypatch.setattr(ai_config_module, "_running_in_docker", lambda: False)
    assert (
        ai_config_module.resolve_llm_base_url("http://host.docker.internal:8080/v1")
        == "http://127.0.0.1:8080/v1"
    )
    assert (
        ai_config_module.resolve_llm_base_url("http://host.docker.internal:8081/v1")
        == "http://127.0.0.1:8080/v1"
    )


def test_resolve_llm_base_url_keeps_localhost_on_bare_metal(monkeypatch):
    monkeypatch.setattr(ai_config_module, "_running_in_docker", lambda: False)
    assert ai_config_module.resolve_llm_base_url("http://127.0.0.1:8080/v1") == "http://127.0.0.1:8080/v1"


def test_resolve_llm_base_url_rewrites_in_docker(monkeypatch):
    monkeypatch.setattr(ai_config_module, "_running_in_docker", lambda: True)
    assert (
        ai_config_module.resolve_llm_base_url("http://127.0.0.1:8080/v1")
        == "http://host.docker.internal:8081/v1"
    )
    assert (
        ai_config_module.resolve_llm_base_url("http://host.docker.internal:8080/v1")
        == "http://host.docker.internal:8081/v1"
    )


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


def test_post_config_preserves_telegram_section(client, isolated_config):
    isolated_config.parent.mkdir(parents=True, exist_ok=True)
    isolated_config.write_bytes(
        b'[telegram]\nbot_token = "123456:ABC"\n\n[llm]\nmodel = "old-model"\n'
    )
    r = client.post("/ai/config", json={"base_url": "http://ollama:11434/v1", "model": "new-model"})
    assert r.status_code == 200

    saved = isolated_config.read_text()
    assert 'bot_token = "123456:ABC"' in saved
    assert 'model = "new-model"' in saved


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


def test_test_connection_ok(client, monkeypatch):
    monkeypatch.setenv("STOW_LLM_MODEL", "qwen3:30b")

    async def fake_run(*args, **kwargs):
        result = MagicMock()
        result.output = "pong"
        return result

    mock_agent = MagicMock()
    mock_agent.run = fake_run

    with patch("pydantic_ai.Agent", return_value=mock_agent):
        r = client.post("/ai/test-connection")
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["model"] == "qwen3:30b"
    assert isinstance(data["latency_ms"], (int, float))


def test_test_connection_failure(client, monkeypatch):
    import httpx

    async def failing_run(*args, **kwargs):
        raise httpx.ConnectError("Connection refused")

    mock_agent = MagicMock()
    mock_agent.run = failing_run

    with patch("pydantic_ai.Agent", return_value=mock_agent):
        r = client.post("/ai/test-connection")
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is False
    assert "Connection refused" in data["error"]
    assert data["latency_ms"] is None


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
    result.output = parsed
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
    result.output = parsed
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
