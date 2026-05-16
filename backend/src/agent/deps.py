from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import httpx


@dataclass
class StowDeps:
    """Shared dependencies for the orchestrator and all subagents."""

    base_url: str
    http_client: httpx.AsyncClient
    # Required by SubAgentDepsProtocol — stores compiled subagent instances
    subagents: dict[str, Any] = field(default_factory=dict)

    def clone_for_subagent(self, max_depth: int = 0) -> StowDeps:
        """Return a fresh deps clone for a subagent invocation.

        Subagents share the HTTP client and base URL but get an empty subagents
        dict (they cannot spawn further subagents by default).
        """
        return StowDeps(
            base_url=self.base_url,
            http_client=self.http_client,
            subagents={} if max_depth <= 0 else dict(self.subagents),
        )
