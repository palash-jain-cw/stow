import os
import tomllib
import tomli_w
from pathlib import Path


_CONFIG_PATH = Path.home() / ".stow" / "config"


def read_config() -> dict:
    base_url = os.environ.get("STOW_LLM_BASE_URL", "")
    model = os.environ.get("STOW_LLM_MODEL", "")
    api_key = os.environ.get("STOW_LLM_API_KEY", "")

    if not (base_url and model):
        file_cfg = _read_file()
        base_url = base_url or file_cfg.get("base_url", "")
        model = model or file_cfg.get("model", "")
        api_key = api_key or file_cfg.get("api_key", "")

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
