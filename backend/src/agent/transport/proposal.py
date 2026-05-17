from __future__ import annotations

import json

PROPOSAL_PREFIX = "PROPOSAL:"


def parse_proposal(text: str) -> tuple[dict | None, str]:
    """Extract a PROPOSAL: JSON line from an orchestrator response.

    Returns (proposal_dict, display_text). proposal_dict is None when no
    valid proposal line is found. display_text has the PROPOSAL: line removed.
    """
    lines = text.splitlines()
    proposal: dict | None = None
    remaining: list[str] = []

    for line in lines:
        if line.startswith(PROPOSAL_PREFIX):
            try:
                proposal = json.loads(line[len(PROPOSAL_PREFIX):])
            except json.JSONDecodeError:
                remaining.append(line)
        else:
            remaining.append(line)

    display = "\n".join(remaining).strip()
    return proposal, display
