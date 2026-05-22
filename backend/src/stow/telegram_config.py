from __future__ import annotations

import logging
import os
import tomllib
import tomli_w
from pathlib import Path

from stow.ai_config import _CONFIG_PATH

logger = logging.getLogger(__name__)


def read_telegram_config() -> dict[str, str]:
    """Return telegram settings. File config takes precedence over env vars."""
    file_cfg = _read_file()
    bot_token = file_cfg.get("bot_token") or os.environ.get("TELEGRAM_BOT_TOKEN", "")
    return {"bot_token": bot_token}


def write_telegram_config(bot_token: str) -> None:
    """Persist bot token to ~/.stow/config under [telegram]."""
    _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    data: dict = {}
    if _CONFIG_PATH.exists():
        with open(_CONFIG_PATH, "rb") as f:
            data = tomllib.load(f)
    data.setdefault("telegram", {})["bot_token"] = bot_token.strip()
    with open(_CONFIG_PATH, "wb") as f:
        tomli_w.dump(data, f)
    logger.info("Telegram bot token saved to config")


def _read_file() -> dict:
    if not _CONFIG_PATH.exists():
        return {}
    with open(_CONFIG_PATH, "rb") as f:
        return tomllib.load(f).get("telegram", {})
