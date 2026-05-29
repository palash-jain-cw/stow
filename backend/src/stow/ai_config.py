from __future__ import annotations

import logging
import os
import tomllib
import tomli_w
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_CONFIG_PATH = Path.home() / ".stow" / "config"


def _running_in_docker() -> bool:
    if os.environ.get("STOW_LLM_NORMALIZE_HOST", "").lower() in ("1", "true", "yes"):
        return True
    return Path("/.dockerenv").exists()


def _llm_proxy_port() -> str:
    return os.environ.get("STOW_LLM_PROXY_PORT", "8081")


def _default_base_url() -> str:
    if _running_in_docker():
        return f"http://host.docker.internal:{_llm_proxy_port()}/v1"
    return "http://127.0.0.1:8080/v1"


def resolve_llm_base_url(url: str) -> str:
    """Pick an LLM base URL that works from the current runtime (Docker container vs host).

    docker-compose llm-proxy listens on host:STOW_LLM_PROXY_PORT (default 8081) and forwards
    to llama on 127.0.0.1:8080. Host-side scripts map the proxy port back to 8080.
    """
    proxy_port = _llm_proxy_port()
    if not url:
        return _default_base_url()
    if _running_in_docker():
        url = url.replace("://localhost", "://host.docker.internal").replace(
            "://127.0.0.1", "://host.docker.internal"
        )
        if ":8080" in url:
            url = url.replace(":8080", f":{proxy_port}")
        return url
    url = url.replace("://host.docker.internal", "://127.0.0.1")
    if f":{proxy_port}" in url:
        url = url.replace(f":{proxy_port}", ":8080")
    return url


def normalize_base_url(url: str) -> str:
    """Backward-compatible alias — prefer resolve_llm_base_url."""
    return resolve_llm_base_url(url)


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
            data = tomllib.load(f)
    llm = data.setdefault("llm", {})
    llm["base_url"] = base_url
    llm["model"] = model
    if api_key:
        llm["api_key"] = api_key
    with open(_CONFIG_PATH, "wb") as f:
        tomli_w.dump(data, f)
    logger.info("LLM config saved (model=%s)", model)


_DEFAULT_BASE_URL = "http://host.docker.internal:8001/v1"
_DEFAULT_MODEL = "Qwen3.6-35B-A3B-MLX-VL-oQ4-FP16"
_DEFAULT_API_KEY = "omlx"

# Local LLM harness — cap generation so a single run cannot fill the context window.
# Override default cap with STOW_LLM_MAX_TOKENS (roles via build_model).
_ROLE_MAX_TOKENS: dict[str, int] = {
    "default": 8192,
    "agent": 16384,
    "parse": 4096,
    "import": 65536,
    "ping": 512,
    "report": 8192,
    "tool_response": 4096,
    "orchestrator": 16384,
}
_DEFAULT_TEMPERATURE = 0.3


def model_settings(role: str = "default", **overrides: Any) -> dict[str, Any]:
    """Model settings for a pydantic-ai run or OpenAIChatModel defaults.

    Roles tune max_tokens for the task; run-level overrides merge on top.
    """
    from pydantic_ai.settings import ModelSettings

    env_cap = os.environ.get("STOW_LLM_MAX_TOKENS")
    if env_cap and role in ("default", "orchestrator"):
        max_tokens = int(env_cap)
    else:
        max_tokens = _ROLE_MAX_TOKENS.get(role, _ROLE_MAX_TOKENS["default"])

    base: ModelSettings = {
        "max_tokens": max_tokens,
        "temperature": _DEFAULT_TEMPERATURE,
        "thinking": False,
    }
    base.update(overrides)  # type: ignore[typeddict-item]
    return base


def _model_profile(model_name: str):
    """Provider-specific tweaks for local llama.cpp + Qwen."""
    from pydantic_ai.profiles.openai import OpenAIModelProfile
    from pydantic_ai.profiles.qwen import qwen_model_profile

    name = model_name.lower()
    base = qwen_model_profile(model_name)
    if "qwen" in name:
        qwen_fixes = OpenAIModelProfile(
            # pydantic-ai sends instructions + a second system block for tools;
            # Qwen's jinja template rejects consecutive system messages unless merged.
            openai_chat_supports_multiple_system_messages=False,
        )
        return qwen_fixes.update(base) if base else qwen_fixes
    return base


def build_model() -> Any:
    from pydantic_ai.models.openai import OpenAIChatModel
    from pydantic_ai.providers.openai import OpenAIProvider
    cfg = read_config()
    using_defaults = not cfg["base_url"]
    base_url = resolve_llm_base_url(cfg["base_url"])
    model_name = cfg["model"] or _DEFAULT_MODEL
    profile = _model_profile(model_name)
    if using_defaults:
        logger.warning(
            "STOW_LLM_BASE_URL not set — using default %s (model=%s). "
            "Set STOW_LLM_* in .env for host-side pytest/scripts.",
            base_url,
            model_name,
        )
    else:
        logger.info("LLM client base_url=%s model=%s", base_url, model_name)
    settings = model_settings("default")
    logger.info(
        "LLM model defaults max_tokens=%s temperature=%s",
        settings.get("max_tokens"),
        settings.get("temperature"),
    )
    return OpenAIChatModel(
        model_name,
        provider=OpenAIProvider(
            base_url=base_url,
            api_key=cfg.get("api_key") or _DEFAULT_API_KEY,
        ),
        profile=profile,
        settings=settings,
    )


def _read_file() -> dict:
    if not _CONFIG_PATH.exists():
        return {}
    with open(_CONFIG_PATH, "rb") as f:
        return tomllib.load(f).get("llm", {})
