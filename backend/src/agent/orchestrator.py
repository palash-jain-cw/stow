from __future__ import annotations

# The orchestrator is now the unified agent.
# All tools from the old subagents are exposed at the top level.
# See agent/agent.py for the complete implementation.

from agent.agent import build_agent, build_orchestrator  # noqa: F401 — backwards compat
