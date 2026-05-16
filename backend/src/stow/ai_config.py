import os
import tomllib
import tomli_w
from pathlib import Path


_CONFIG_PATH = Path.home() / ".stow" / "config"


def normalize_base_url(url: str) -> str:
    """Rewrite localhost/127.0.0.1 → host.docker.internal so the Docker-hosted backend can reach host services."""
    return url.replace("://localhost", "://host.docker.internal").replace("://127.0.0.1", "://host.docker.internal")


def read_config() -> dict:
    # File config (written by UI) takes precedence; env vars are fallback defaults.
    file_cfg = _read_file()
    base_url = file_cfg.get("base_url") or os.environ.get("STOW_LLM_BASE_URL", "")
    model = file_cfg.get("model") or os.environ.get("STOW_LLM_MODEL", "")
    api_key = file_cfg.get("api_key") or os.environ.get("STOW_LLM_API_KEY", "")
    return {"base_url": base_url, "model": model, "api_key": api_key}


def write_config(base_url: str, model: str, api_key: str = "") -> None:
    _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    data: dict = {}
    if _CONFIG_PATH.exists():
        with open(_CONFIG_PATH, "rb") as f:
            data = tomllib.load(f).get("llm", {})
    data["base_url"] = base_url
    data["model"] = model
    if api_key:
        data["api_key"] = api_key
    with open(_CONFIG_PATH, "wb") as f:
        tomli_w.dump({"llm": data}, f)


def _read_file() -> dict:
    if not _CONFIG_PATH.exists():
        return {}
    with open(_CONFIG_PATH, "rb") as f:
        return tomllib.load(f).get("llm", {})
