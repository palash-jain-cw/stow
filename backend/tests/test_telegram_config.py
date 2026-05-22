from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

import stow.ai_config as ai_config_module
import stow.telegram_config as telegram_config_module


@pytest.fixture()
def isolated_config(tmp_path, monkeypatch):
    """Redirect ~/.stow/config to a temp dir so tests don't touch real config."""
    fake_config = tmp_path / ".stow" / "config"
    monkeypatch.setattr(ai_config_module, "_CONFIG_PATH", fake_config)
    monkeypatch.setattr(telegram_config_module, "_CONFIG_PATH", fake_config)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    return fake_config


def test_get_config_returns_not_configured(client, isolated_config):
    r = client.get("/telegram/config")
    assert r.status_code == 200
    data = r.json()
    assert data["configured"] is False
    assert data["bot_username"] is None
    assert data["linked_users"] == []


def test_get_config_reads_env_var(client, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:ABC-test-token")
    with patch(
        "stow.routers.telegram._fetch_bot_info",
        new=AsyncMock(return_value={"username": "stow_bot", "first_name": "Stow"}),
    ):
        r = client.get("/telegram/config")
    assert r.status_code == 200
    data = r.json()
    assert data["configured"] is True
    assert data["bot_username"] == "stow_bot"


def test_post_config_persists_and_get_reads_it(client, isolated_config):
    with patch("agent.transport.telegram.bot.reload_bot", new=AsyncMock(return_value=True)):
        with patch(
            "stow.routers.telegram._fetch_bot_info",
            new=AsyncMock(return_value={"username": "my_bot", "first_name": "My Bot"}),
        ):
            r = client.post("/telegram/config", json={"bot_token": "123456:ABC-test-token"})
    assert r.status_code == 200
    data = r.json()
    assert data["configured"] is True
    assert data["bot_username"] == "my_bot"
    assert isolated_config.exists()
    assert telegram_config_module.read_telegram_config()["bot_token"] == "123456:ABC-test-token"


def test_test_connection_ok(client, isolated_config):
    with patch(
        "stow.routers.telegram._fetch_bot_info",
        new=AsyncMock(return_value={"username": "stow_bot", "first_name": "Stow"}),
    ):
        r = client.post("/telegram/test-connection", json={"bot_token": "123456:ABC-test-token"})
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["bot_username"] == "stow_bot"
    assert data["bot_name"] == "Stow"


def test_test_connection_failure(client, isolated_config):
    with patch(
        "stow.routers.telegram._fetch_bot_info",
        new=AsyncMock(side_effect=ValueError("Unauthorized")),
    ):
        r = client.post("/telegram/test-connection", json={"bot_token": "bad-token"})
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is False
    assert "Unauthorized" in (data["error"] or "")


def test_post_config_rejects_invalid_token(client, isolated_config):
    r = client.post("/telegram/config", json={"bot_token": "not-a-valid-token"})
    assert r.status_code == 400


def test_test_connection_requires_token(client, isolated_config):
    r = client.post("/telegram/test-connection", json={"bot_token": ""})
    assert r.status_code == 200
    assert r.json()["ok"] is False
