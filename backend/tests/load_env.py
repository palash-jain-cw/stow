"""Load LLM env vars from .env files before tests or scripts import stow.ai_config."""
from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

# Never pull DATABASE_URL from .env — tests use testcontainers.
_ENV_PREFIXES = ("STOW_LLM_", "STOW_BASE_URL", "TELEGRAM_")


def _strip_quotes(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def _parse_env_file(path: Path) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, raw = line.partition("=")
        key = key.strip()
        if not any(key.startswith(prefix) for prefix in _ENV_PREFIXES):
            continue
        parsed[key] = _strip_quotes(raw)
    return parsed


def load_llm_env() -> list[Path]:
    """Load STOW_LLM_* (and related) vars from repo .env files. Returns paths loaded."""
    backend_dir = Path(__file__).resolve().parent.parent
    candidates = [
        backend_dir.parent / ".env",
        backend_dir / ".env",
    ]
    loaded: list[Path] = []
    for path in candidates:
        if not path.exists():
            continue
        for key, value in _parse_env_file(path).items():
            os.environ.setdefault(key, value)
        loaded.append(path)
        logger.info("Loaded LLM env from %s", path)
    return loaded
