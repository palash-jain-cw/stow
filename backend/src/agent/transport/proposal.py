from __future__ import annotations

import json
import logging
import traceback
import uuid
from typing import Any

import httpx

from agent.tool_errors import ProposalActionResult, format_tool_error

logger = logging.getLogger(__name__)

PROPOSAL_PREFIX = "PROPOSAL:"

_REQUIRED_FIELDS = ("type", "date", "from_account_id", "to_account_id", "fy_id")

# user_key -> {proposal_id: normalized proposal}
_pending: dict[str, dict[str, dict[str, Any]]] = {}
# user_key -> most recently stored proposal_id (for plain "confirm")
_latest_pending: dict[str, str] = {}

_CONFIRM_WORDS = frozenset({"confirm", "yes", "post", "ok", "y"})
_DECLINE_WORDS = frozenset({"decline", "cancel", "discard", "no", "n"})


def _normalize_tags(raw: Any) -> list[str] | None:
    """Return a deduplicated list of non-empty tag strings, or None if absent/empty."""
    if raw is None:
        return None
    if not isinstance(raw, list):
        raise ValueError("tags must be a list of strings")
    tags: list[str] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, str):
            raise ValueError("tags must be a list of strings")
        tag = item.strip()
        if tag and tag.lower() not in seen:
            seen.add(tag.lower())
            tags.append(tag)
    return tags or None


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
            except json.JSONDecodeError as exc:
                logger.warning("Invalid PROPOSAL JSON: %s", exc)
                remaining.append(line)
        else:
            remaining.append(line)

    display = "\n".join(remaining).strip()
    return proposal, display


def normalize_proposal(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalize orchestrator/subagent proposal JSON to the confirm/post schema."""
    data = dict(raw)

    if "amount_paise" not in data and "amount" in data:
        data["amount_paise"] = data["amount"]

    if isinstance(data.get("date"), str):
        data["date"] = data["date"][:10]

    missing = [field for field in _REQUIRED_FIELDS if data.get(field) in (None, "")]
    amount = data.get("amount_paise")
    if not isinstance(amount, int) or amount <= 0:
        missing.append("amount_paise")

    if missing:
        raise ValueError(f"Proposal missing or invalid fields: {', '.join(missing)}")

    data.setdefault("narration", data.get("narration") or "")
    data.setdefault("from_account_name", data.get("from_account_name") or "")
    data.setdefault("to_account_name", data.get("to_account_name") or "")
    if "tags" in data:
        data["tags"] = _normalize_tags(data.get("tags"))
    return data


def store_pending(user_key: str, proposal: dict[str, Any]) -> str:
    """Store a proposal for later confirm/decline. Returns a short callback id."""
    normalized = normalize_proposal(proposal)
    proposal_id = uuid.uuid4().hex[:8]
    _pending.setdefault(user_key, {})[proposal_id] = normalized
    _latest_pending[user_key] = proposal_id
    logger.info("Stored pending proposal %s for user %s", proposal_id, user_key)
    return proposal_id


def pop_latest_pending(user_key: str) -> dict[str, Any] | None:
    """Remove and return the most recently stored proposal for this user/session."""
    proposal_id = _latest_pending.pop(user_key, None)
    if proposal_id is None:
        return None
    bucket = _pending.get(user_key, {})
    proposal = bucket.pop(proposal_id, None)
    if not bucket:
        _pending.pop(user_key, None)
    return proposal


def pop_pending(user_key: str, proposal_id: str) -> dict[str, Any] | None:
    """Remove and return a pending proposal, if it exists."""
    proposal = _pending.get(user_key, {}).pop(proposal_id, None)
    if proposal_id == _latest_pending.get(user_key):
        _latest_pending.pop(user_key, None)
    return proposal


def clear_pending_for_user(user_key: str) -> None:
    _pending.pop(user_key, None)
    _latest_pending.pop(user_key, None)


async def execute_proposal(
    proposal: dict[str, Any],
    http_client: httpx.AsyncClient,
    base_url: str,
) -> dict[str, Any] | str:
    """Post a confirmed proposal directly to POST /transactions."""
    try:
        data = normalize_proposal(proposal)
    except ValueError as exc:
        logger.error("execute_proposal invalid proposal: %s", traceback.format_exc())
        return format_tool_error("confirm_transaction", exc)

    payload = {
        "type": data["type"],
        "date": data["date"],
        "narration": data["narration"],
        "fy_id": data["fy_id"],
        "entries": [
            {"account_id": data["from_account_id"], "amount": -data["amount_paise"]},
            {"account_id": data["to_account_id"], "amount": data["amount_paise"]},
        ],
    }
    if data.get("tags"):
        payload["tags"] = data["tags"]
    try:
        response = await http_client.post(f"{base_url}/transactions", json=payload)
        response.raise_for_status()
    except Exception as exc:
        logger.error("execute_proposal failed: %s", traceback.format_exc())
        return format_tool_error("confirm_transaction", exc)

    txn = response.json()
    logger.info("Posted transaction %s from proposal", txn.get("number"))
    return txn


def format_post_success(txn: dict[str, Any]) -> str:
    number = txn.get("number", "transaction")
    narration = txn.get("narration") or "Entry posted"
    return f"✓ Posted {number} — {narration}"


def _agent_retry_prompt(error: str, proposal: dict[str, Any]) -> str:
    return (
        f"The user confirmed the pending transaction but posting failed.\n"
        f"Failure: {error}\n"
        f"Pending proposal JSON: {json.dumps(proposal, ensure_ascii=False)}\n"
        "Diagnose the problem, fix any account/FY/amount issues, and emit an updated PROPOSAL "
        "or ask the user one clarifying question."
    )


async def _confirm_proposal_data(
    proposal: dict[str, Any],
    http_client: httpx.AsyncClient,
    base_url: str,
    *,
    user_key: str | None,
) -> ProposalActionResult:
    result = await execute_proposal(proposal, http_client, base_url)
    if isinstance(result, str):
        if user_key:
            try:
                store_pending(user_key, proposal)
            except ValueError:
                logger.warning("Could not re-store invalid proposal after confirm failure")
        return ProposalActionResult("agent", _agent_retry_prompt(result, proposal))
    return ProposalActionResult("reply", format_post_success(result))


async def handle_proposal_action(
    message: str,
    http_client: httpx.AsyncClient,
    base_url: str,
    *,
    user_key: str | None = None,
) -> ProposalActionResult:
    """Handle confirm/decline messages. Failures route back to the orchestrator."""
    text = message.strip()
    if not text:
        return ProposalActionResult("none")

    lowered = text.lower()
    if lowered in _DECLINE_WORDS:
        if user_key:
            pop_latest_pending(user_key)
        return ProposalActionResult("reply", "Transaction discarded.")

    if lowered in _CONFIRM_WORDS:
        if user_key is None:
            return ProposalActionResult("none")
        proposal = pop_latest_pending(user_key)
        if proposal is None:
            return ProposalActionResult(
                "agent",
                "The user said confirm but there is no pending transaction proposal. "
                "Ask what they want to confirm or help them describe the transaction again.",
            )
        return await _confirm_proposal_data(proposal, http_client, base_url, user_key=user_key)

    if text.startswith("confirm:"):
        raw_json = text[len("confirm:"):].strip()
        try:
            raw = json.loads(raw_json)
        except json.JSONDecodeError as exc:
            logger.error("Invalid confirm JSON: %s", traceback.format_exc())
            return ProposalActionResult(
                "agent",
                f"Could not parse confirm JSON: {exc}. Ask the user to confirm again or re-propose.",
            )
        return await _confirm_proposal_data(raw, http_client, base_url, user_key=user_key)

    if text.startswith("cfm:"):
        return ProposalActionResult("none")

    return ProposalActionResult("none")


async def try_handle_proposal_action(
    message: str,
    http_client: httpx.AsyncClient,
    base_url: str,
    *,
    user_key: str | None = None,
) -> str | None:
    """Backward-compatible helper — returns reply text or None (use handle_proposal_action for agent routing)."""
    result = await handle_proposal_action(
        message, http_client, base_url, user_key=user_key
    )
    if result.kind == "reply":
        return result.message
    return None


async def confirm_pending_proposal(
    user_key: str,
    proposal_id: str,
    http_client: httpx.AsyncClient,
    base_url: str,
) -> ProposalActionResult:
    proposal = pop_pending(user_key, proposal_id)
    if proposal is None:
        return ProposalActionResult(
            "reply",
            "That proposal expired. Please describe the transaction again.",
        )
    return await _confirm_proposal_data(
        proposal, http_client, base_url, user_key=user_key
    )


def decline_pending_proposal(user_key: str, proposal_id: str) -> str:
    pop_pending(user_key, proposal_id)
    return "Transaction discarded."
