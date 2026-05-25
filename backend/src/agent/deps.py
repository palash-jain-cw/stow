from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass
class StowDeps:
    """Shared dependencies for the unified Stow agent."""

    base_url: str
    http_client: httpx.AsyncClient

    @classmethod
    def build(cls) -> StowDeps:
        """Create deps from environment. Caller owns the http_client lifecycle."""
        return cls(
            base_url=os.environ.get("STOW_BASE_URL", "http://localhost:8000"),
            http_client=httpx.AsyncClient(timeout=60.0),
        )
