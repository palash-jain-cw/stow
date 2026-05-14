import pytest
from stow.config import Settings


def test_settings_reads_env_vars(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@localhost/stow")
    monkeypatch.setenv("STOW_LLM_BASE_URL", "http://localhost:11434/v1")
    monkeypatch.setenv("STOW_LLM_MODEL", "qwen3:8b")

    s = Settings()

    assert s.database_url == "postgresql://u:p@localhost/stow"
    assert s.stow_llm_base_url == "http://localhost:11434/v1"
    assert s.stow_llm_model == "qwen3:8b"
